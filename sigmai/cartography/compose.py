"""Compositor de mapas do SIGMAI.

Substitui ``generate_professional_map``. As diferenças que importam:

* a página é escolhida e respeitada (A5 a A0, retrato ou paisagem), em vez de
  milímetros fixos para A4 paisagem;
* a extensão é ajustada à razão de aspecto do quadro e fechada numa escala da
  série cartográfica, com a margem efetiva declarada;
* a grade recebe um intervalo calculado — habilitá-la sem intervalo, como o
  motor antigo fazia, não desenha nada;
* a legenda lista **todas** as camadas visíveis do quadro, não só a principal;
* a barra de escala é dimensionada para ocupar uma fração legível do quadro;
* a rosa dos ventos é um símbolo do QGIS ligado ao norte da grade, não a
  letra "N" escrita num rótulo;
* o layout declara datum/projeção e data;
* o resultado é auditado pelo regulamento e o laudo volta junto, com as
  correções concretas — é esse texto que permite ao agente de IA iterar.
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import replace
from pathlib import Path
from typing import Any

from .layoutgrid import DEFAULT_TEMPLATE, TEMPLATES, LayoutPlan, Rect, solve_layout
from .pagespec import PageSpec, resolve_page
from .qtcompat import distance_unit, layout_unit_mm, qt_enum
from .rulebook import evaluate
from .scaling import fit_extent_to_frame, graticule_interval, scalebar_spec
from .symbology import apply_default_symbology

#: SVG de norte preferidos, do mais sóbrio para o mais decorativo. O primeiro
#: que existir na instalação do QGIS é usado.
NORTH_ARROW_CANDIDATES = (
    "arrows/NorthArrow_02.svg",
    "arrows/NorthArrow_11.svg",
    "arrows/NorthArrow_01.svg",
    "arrows/NorthArrow_04.svg",
)

#: SIRGAS 2000 / UTM — o datum oficial brasileiro. Fora da faixa, o compositor
#: cai para WGS 84 / UTM.
_SIRGAS_UTM_NORTH_BASE = 31965  # zona 11N
_SIRGAS_UTM_SOUTH_BASE = 31977  # zona 17S


class CompositionError(RuntimeError):
    """Falha irrecuperável ao compor o mapa."""


def _imports() -> dict[str, Any]:
    try:
        from qgis.PyQt.QtGui import QColor, QFont  # type: ignore
        from qgis.core import (  # type: ignore
            Qgis,
            QgsApplication,
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsDistanceArea,
            QgsLayoutExporter,
            QgsLayoutItemLabel,
            QgsLayoutItemLegend,
            QgsLayoutItemMap,
            QgsLayoutItemMapGrid,
            QgsLayoutItemPage,
            QgsLayoutItemPicture,
            QgsLayoutItemScaleBar,
            QgsLayoutPoint,
            QgsPointXY,
            QgsLayoutSize,
            QgsPrintLayout,
            QgsProject,
            QgsRectangle,
            QgsUnitTypes,
        )
    except Exception as exc:  # pragma: no cover - só ocorre fora do QGIS
        raise CompositionError("O compositor cartográfico exige PyQGIS (executar dentro do QGIS).") from exc
    # locals() precisa ser materializado fora da compreensão: dentro dela o
    # escopo é o da própria compreensão, e o dicionário sairia vazio.
    resolved = dict(locals())
    return {name: value for name, value in resolved.items() if name not in {"exc", "resolved"}}


# ---------------------------------------------------------------------------
# Utilitários de projeto
# ---------------------------------------------------------------------------

def _resolve_layers(params: dict[str, Any], imports: dict[str, Any]) -> list[Any]:
    project = imports["QgsProject"].instance()
    raw = params.get("layer_ids") or params.get("layers") or params.get("layer_id")
    if isinstance(raw, str):
        raw = [raw]
    if not raw:
        raise CompositionError("Informe layer_ids com pelo menos uma camada.")
    layers = []
    missing = []
    for layer_id in raw:
        layer = project.mapLayer(str(layer_id))
        if layer is None:
            # Aceita nome além de id: agentes erram o id com frequência, e um
            # erro claro vale mais que um mapa vazio.
            matches = project.mapLayersByName(str(layer_id))
            layer = matches[0] if matches else None
        if layer is None:
            missing.append(str(layer_id))
        else:
            layers.append(layer)
    if missing:
        available = [f"{layer.name()} ({layer.id()})" for layer in project.mapLayers().values()]
        raise CompositionError(
            f"Camadas não encontradas: {', '.join(missing)}. Disponíveis: {'; '.join(available) or 'nenhuma'}."
        )
    return layers


def _combined_extent(layers: list[Any], target_crs: Any, imports: dict[str, Any]) -> Any:
    project = imports["QgsProject"].instance()
    combined = None
    for layer in layers:
        rect = layer.extent()
        if rect is None or rect.isEmpty():
            continue
        try:
            source_crs = layer.crs()
            if source_crs.isValid() and target_crs.isValid() and source_crs.authid() != target_crs.authid():
                transform = imports["QgsCoordinateTransform"](source_crs, target_crs, project)
                rect = transform.transformBoundingBox(rect)
        except Exception:
            continue
        combined = imports["QgsRectangle"](rect) if combined is None else combined
        if combined is not rect:
            combined.combineExtentWith(rect)
    if combined is None or combined.isEmpty():
        raise CompositionError("As camadas informadas não têm extensão válida (todas vazias?).")
    return combined


def _map_units_per_metre(crs: Any, extent: Any, imports: dict[str, Any]) -> float:
    """Quantas unidades do CRS cabem num metro, ao longo da extensão.

    Para CRS projetados métricos é 1. Para CRS geográficos, um grau não tem
    comprimento constante: ~111 km no equador e zero nos polos. Sem esta
    conversão, ``scale_from_extent`` trata graus como metros e devolve uma
    escala sem sentido — o Piauí inteiro saía como 1:65.
    """
    if not crs.isGeographic():
        return 1.0
    try:
        calculator = imports["QgsDistanceArea"]()
        calculator.setSourceCrs(crs, imports["QgsProject"].instance().transformContext())
        calculator.setEllipsoid(crs.ellipsoidAcronym() or "WGS84")
        middle_y = (extent.yMinimum() + extent.yMaximum()) / 2.0
        metres = calculator.measureLine(
            imports["QgsPointXY"](extent.xMinimum(), middle_y),
            imports["QgsPointXY"](extent.xMaximum(), middle_y),
        )
        if metres > 0:
            return extent.width() / metres
    except Exception:
        pass
    # Recurso final: comprimento de um grau de longitude na latitude central.
    import math

    latitude = math.radians((extent.yMinimum() + extent.yMaximum()) / 2.0)
    metres_per_degree = 111_320.0 * max(0.05, math.cos(latitude))
    return 1.0 / metres_per_degree


#: Limite em graus para cada estratégia de projeção automática.
#:
#: Uma zona UTM tem 6° de largura e o fator de escala só fica dentro de 1/1000
#: até cerca de 3° do meridiano central. Um recorte que ultrapasse ~4,5° de
#: longitude já projeta terreno a mais de 300 km do meridiano, onde a distorção
#: passa de meio por cento e as coordenadas saem da faixa válida da zona — foi o
#: que aconteceu ao mapear o Piauí inteiro em UTM 23S, com eastings de
#: 1.250.000 numa zona que vai até 834.000.
UTM_MAX_LONGITUDE_SPAN_DEGREES = 4.5
UTM_MAX_LATITUDE_SPAN_DEGREES = 12.0
REGIONAL_MAX_SPAN_DEGREES = 40.0

#: Caixa aproximada do território brasileiro, para escolher a Policônica.
BRAZIL_BOUNDS = (-74.0, -34.0, -34.0, 6.0)


def _suggest_projected_crs(extent: Any, source_crs: Any, imports: dict[str, Any]) -> tuple[Any, str]:
    """Escolhe um UTM adequado para uma extensão em coordenadas geográficas."""
    centre_lon = (extent.xMinimum() + extent.xMaximum()) / 2.0
    centre_lat = (extent.yMinimum() + extent.yMaximum()) / 2.0
    span = max(extent.width(), extent.height())

    # O UTM é julgado pelo alcance em longitude, não pelo maior dos dois eixos:
    # é o afastamento do meridiano central que gera distorção. Um recorte alto
    # e estreito continua servido pelo UTM; um largo, não.
    if extent.width() > UTM_MAX_LONGITUDE_SPAN_DEGREES or extent.height() > UTM_MAX_LATITUDE_SPAN_DEGREES:
        return _suggest_regional_crs(extent, centre_lon, centre_lat, span, imports)

    zone = int((centre_lon + 180.0) / 6.0) + 1
    zone = max(1, min(60, zone))
    northern = centre_lat >= 0

    datum = str(source_crs.description() or "").lower() + " " + str(source_crs.authid() or "")
    candidates: list[tuple[str, str]] = []
    if "sirgas" in datum or source_crs.authid() == "EPSG:4674":
        if northern and 11 <= zone <= 22:
            candidates.append((f"EPSG:{_SIRGAS_UTM_NORTH_BASE + (zone - 11)}", "SIRGAS 2000 / UTM"))
        elif not northern and 17 <= zone <= 25:
            candidates.append((f"EPSG:{_SIRGAS_UTM_SOUTH_BASE + (zone - 17)}", "SIRGAS 2000 / UTM"))
    candidates.append((f"EPSG:{(32600 if northern else 32700) + zone}", "WGS 84 / UTM"))

    for authid, family in candidates:
        crs = imports["QgsCoordinateReferenceSystem"](authid)
        if crs.isValid():
            hemisphere = "N" if northern else "S"
            return crs, f"{family} zona {zone}{hemisphere} ({authid})"
    return source_crs, ""


def _suggest_regional_crs(
    extent: Any, centre_lon: float, centre_lat: float, span: float, imports: dict[str, Any]
) -> tuple[Any, str]:
    """Projeção para extensões grandes demais para uma zona UTM."""
    if span > REGIONAL_MAX_SPAN_DEGREES:
        # Escala continental: qualquer projeção plana distorce muito, e a
        # escolha passa a ser editorial. O compositor não decide por conta.
        return None, ""

    west, south, east, north = BRAZIL_BOUNDS
    inside_brazil = (
        west <= extent.xMinimum() and extent.xMaximum() <= east
        and south <= extent.yMinimum() and extent.yMaximum() <= north
    )
    if inside_brazil:
        polyconic = imports["QgsCoordinateReferenceSystem"]("EPSG:5880")
        if polyconic.isValid():
            return polyconic, "SIRGAS 2000 / Policônica do Brasil (EPSG:5880)"

    # Lambert Azimutal de Áreas Iguais centrada na extensão: é a escolha
    # convencional para mapas regionais temáticos quando não há um sistema
    # oficial aplicável.
    proj = (
        f"+proj=laea +lat_0={centre_lat:.4f} +lon_0={centre_lon:.4f} "
        "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    laea = imports["QgsCoordinateReferenceSystem"]()
    try:
        laea.createFromProj(proj)
    except Exception:
        try:
            laea.createFromProj4(proj)
        except Exception:
            return None, ""
    if laea.isValid():
        return laea, (
            f"Lambert Azimutal de Áreas Iguais centrada em "
            f"{abs(centre_lat):.2f}°{'S' if centre_lat < 0 else 'N'}, "
            f"{abs(centre_lon):.2f}°{'W' if centre_lon < 0 else 'E'}"
        )
    return None, ""


def _find_north_arrow_svg(imports: dict[str, Any]) -> str:
    for base in imports["QgsApplication"].svgPaths():
        for relative in NORTH_ARROW_CANDIDATES:
            candidate = Path(base) / relative
            if candidate.exists():
                return str(candidate)
    return ""


def _format_scale(denominator: int) -> str:
    return f"1:{denominator:,}".replace(",", ".")


def _credit_line(params: dict[str, Any], crs_label: str, date_label: str) -> str:
    pieces = []
    source = str(params.get("data_source", "")).strip()
    if source:
        pieces.append(f"Fonte: {source}")
    author = str(params.get("map_author", "")).strip()
    if author:
        pieces.append(f"Elaboração: {author}")
    organization = str(params.get("organization", "")).strip()
    if organization:
        pieces.append(organization)
    if crs_label:
        pieces.append(crs_label)
    if date_label:
        pieces.append(date_label)
    pieces.append("Produzido com SIGMAI/QGIS")
    return " · ".join(pieces)


# ---------------------------------------------------------------------------
# Compositor
# ---------------------------------------------------------------------------

def compose_map(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Compõe, exporta e audita um mapa completo."""
    imports = _imports()
    project = imports["QgsProject"].instance()

    layers = _resolve_layers(params, imports)
    styling = apply_default_symbology(layers, str(params.get("apply_style", "missing")))
    page: PageSpec = resolve_page(params.get("page"), params.get("orientation"), params.get("margin_mm"))
    template = str(params.get("template", params.get("layout_template", DEFAULT_TEMPLATE)))

    include_legend = bool(params.get("include_legend", True))
    include_scale_bar = bool(params.get("include_scale_bar", True))
    include_scale_text = bool(params.get("include_scale_text", True))
    include_north = bool(params.get("include_north_arrow", True))
    include_grid = bool(params.get("include_grid", True))
    include_subtitle = bool(str(params.get("subtitle", "")).strip())
    include_logo = bool(params.get("include_logo", False))

    # O corredor precisa caber o rótulo mais longo da grade. Coordenadas UTM
    # têm 7 dígitos; escritas na vertical nas laterais, consomem a altura da
    # linha, não a largura do texto.
    annotation_gutter = 0.0
    if include_grid:
        base_font = TEMPLATES.get(template, TEMPLATES[DEFAULT_TEMPLATE])["footer_font_pt"]
        annotation_gutter = max(5.0, float(base_font) * 0.62)

    plan = solve_layout(
        page=page,
        template=template,
        include_legend=include_legend,
        include_scale_bar=include_scale_bar,
        include_scale_text=include_scale_text,
        include_north_arrow=include_north,
        include_subtitle=include_subtitle,
        include_logo=include_logo,
        grid_annotation_gutter_mm=annotation_gutter,
    )
    frame = plan.map_frame()

    # --- sistema de referência ------------------------------------------
    notes: list[str] = list(plan.notes)
    requested_crs = str(params.get("map_crs", "")).strip()
    if requested_crs:
        map_crs = imports["QgsCoordinateReferenceSystem"](requested_crs)
        if not map_crs.isValid():
            raise CompositionError(f"map_crs inválido: {requested_crs}")
    else:
        map_crs = project.crs()

    extent = _combined_extent(layers, map_crs, imports)

    if map_crs.isGeographic() and bool(params.get("auto_projected_crs", True)):
        projected, label = _suggest_projected_crs(extent, map_crs, imports)
        if projected is not None and label:
            map_crs = projected
            extent = _combined_extent(layers, map_crs, imports)
            notes.append(
                f"O projeto está em coordenadas geográficas; o mapa foi reprojetado para {label} "
                "para que escala, barra e medidas sejam métricas. Passe auto_projected_crs=false para desligar."
            )
        elif map_crs.isGeographic():
            notes.append(
                "A extensão é grande demais para uma projeção regional automática; o mapa continua em "
                "coordenadas geográficas. A escala é aproximada e a barra de escala não é confiável — "
                "escolha uma projeção adequada com map_crs."
            )

    fitted = fit_extent_to_frame(
        extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum(),
        frame.width, frame.height,
        margin_percent=float(params.get("margin_percent", 5.0)),
        snap_to_round_scale=bool(params.get("round_scale", True)),
        map_units_per_metre=_map_units_per_metre(map_crs, extent, imports),
    )
    notes.extend(fitted.notes)

    notes.extend(
        _orientation_advice(
            extent, frame, page, template, gutter=annotation_gutter,
            include_legend=include_legend, include_scale_bar=include_scale_bar,
            include_scale_text=include_scale_text, include_north=include_north,
            include_subtitle=include_subtitle, include_logo=include_logo,
        )
    )

    layout_name = str(params.get("layout_name") or _unique_layout_name(project, params.get("title", "Mapa SIGMAI")))
    output_path = Path(str(params.get("output_path", ""))).expanduser() if params.get("output_path") else None
    export_format = str(params.get("format", (output_path.suffix.lstrip(".") if output_path else "pdf"))).lower()

    if context.get("dry_run"):
        return {
            "dry_run": True,
            "layout_name": layout_name,
            "plan": plan.to_dict(),
            "map_crs": map_crs.authid(),
            "extent": fitted.to_dict(),
            "scale": _format_scale(fitted.scale_denominator),
            "layers": [{"id": layer.id(), "name": layer.name()} for layer in layers],
            "output_path": str(output_path) if output_path else "",
            "format": export_format,
            "notes": notes,
        }

    if output_path is not None:
        if not output_path.parent.exists():
            raise CompositionError(f"A pasta de saída não existe: {output_path.parent}")
        if output_path.exists() and not bool(params.get("confirm_overwrite", False)):
            raise CompositionError(
                f"O arquivo já existe: {output_path}. Passe confirm_overwrite=true para substituí-lo."
            )

    # --- layout -----------------------------------------------------------
    layout = imports["QgsPrintLayout"](project)
    layout.initializeDefaults()
    layout.setName(layout_name)
    _apply_page_size(layout, page, imports)
    project.layoutManager().addLayout(layout)

    created: dict[str, str] = {}
    mm = layout_unit_mm(imports["Qgis"], imports["QgsUnitTypes"])

    # Mapa
    map_item = imports["QgsLayoutItemMap"](layout)
    map_item.setId("main_map")
    layout.addLayoutItem(map_item)
    _place(map_item, frame, imports, mm)
    map_item.setCrs(map_crs)
    map_item.setLayers(layers)
    map_item.setExtent(imports["QgsRectangle"](fitted.xmin, fitted.ymin, fitted.xmax, fitted.ymax))
    # setScale recentraliza a extensão na escala pedida. Se a escala calculada
    # divergir da que o QGIS deriva da extensão — o que acontece quando o CRS é
    # geográfico e a conversão para metros é aproximada — aplicá-la encolhe o
    # quadro e corta os dados. Só se aplica quando as duas concordam.
    try:
        derived = float(map_item.scale())
        target = float(fitted.scale_denominator)
        if derived > 0 and abs(derived - target) / target <= 0.02:
            map_item.setScale(target)
        elif derived > 0:
            notes.append(
                f"Escala derivada pelo QGIS ({derived:,.0f}) difere da calculada ({target:,.0f}); "
                "mantida a extensão ajustada para não cortar dados.".replace(",", ".")
            )
            fitted = replace(fitted, scale_denominator=int(round(derived)))
    except Exception:
        pass
    map_item.setFrameEnabled(True)
    created["main_map"] = "map"

    if include_grid:
        _apply_grid(map_item, fitted, map_crs, plan, imports, notes, str(params.get("grid_style", "solid")))
        created["grid"] = "grid"

    # Título e subtítulo
    title_text = str(params.get("title", "")).strip() or "Mapa"
    _add_label(layout, "title", title_text, plan.slots["title"], plan.fonts["title"], imports, mm, bold=True, align="center")
    created["title"] = "label"
    if include_subtitle and "subtitle" in plan.slots:
        _add_label(layout, "subtitle", str(params["subtitle"]).strip(), plan.slots["subtitle"], plan.fonts["subtitle"], imports, mm, align="center")
        created["subtitle"] = "label"

    # Legenda com TODAS as camadas do quadro
    if include_legend and "legend" in plan.slots:
        _add_legend(layout, map_item, layers, plan, params, imports, mm)
        created["legend"] = "legend"

    # Barra de escala dimensionada
    bar_slot_width = plan.slots["scale_bar"].width if "scale_bar" in plan.slots else frame.width
    bar_spec = scalebar_spec(
        fitted.scale_denominator,
        frame.width,
        # 0,70 e não 0,88: o item do QGIS desenha os rótulos ultrapassando as
        # extremidades da barra, e o excedente precisa caber na faixa.
        max_width_mm=max(12.0, bar_slot_width * 0.70),
    )
    if include_scale_bar and "scale_bar" in plan.slots:
        _add_scalebar(layout, map_item, bar_spec, plan, imports, mm, page)
        created["scale_bar"] = "scalebar"

    # Escala numérica
    if include_scale_text and "scale_text" in plan.slots:
        _add_label(
            layout, "scale_text", f"Escala {_format_scale(fitted.scale_denominator)}",
            plan.slots["scale_text"], plan.fonts["scale_text"], imports, mm, align="center",
        )
        created["scale_text"] = "label"

    # Rosa dos ventos como símbolo
    if include_north and "north" in plan.slots:
        kind = _add_north_arrow(layout, map_item, plan.slots["north"], imports, mm, notes)
        created["north_arrow"] = kind

    # Rodapé: fonte, autoria, CRS e data
    crs_label = f"{map_crs.description() or map_crs.authid()} ({map_crs.authid()})"
    date_label = str(params.get("production_date") or _datetime.date.today().strftime("%d/%m/%Y"))
    _add_label(
        layout, "source", _credit_line(params, crs_label, date_label),
        plan.slots["footer"], plan.fonts["footer"], imports, mm, align="left",
    )
    created["source"] = "label"

    if include_logo and "logo" in plan.slots:
        logo_path = str(params.get("logo_path", "")).strip()
        if logo_path and Path(logo_path).exists():
            picture = imports["QgsLayoutItemPicture"](layout)
            picture.setId("logo")
            picture.setPicturePath(logo_path)
            layout.addLayoutItem(picture)
            _place(picture, plan.slots["logo"], imports, mm)
            created["logo"] = "picture"

    layout.refresh()
    try:
        map_item.refresh()
    except Exception:
        pass

    # --- exportação -------------------------------------------------------
    export_result: dict[str, Any] = {"exported": False}
    if output_path is not None:
        export_result = _export(layout, output_path, export_format, params, imports)

    # --- auditoria --------------------------------------------------------
    audit = audit_layout(
        layout,
        page=page,
        output_path=str(output_path) if output_path else None,
        data_extent={
            "xmin": extent.xMinimum(), "ymin": extent.yMinimum(),
            "xmax": extent.xMaximum(), "ymax": extent.yMaximum(),
        },
        map_frame=frame,
    )

    return {
        "layout_name": layout_name,
        "template": plan.template,
        "arrangement": plan.arrangement,
        "page": page.to_dict(),
        "map_crs": map_crs.authid(),
        "map_crs_description": map_crs.description(),
        "scale": _format_scale(fitted.scale_denominator),
        "scale_denominator": fitted.scale_denominator,
        "extent": fitted.to_dict(),
        "scale_bar": bar_spec.to_dict(),
        "layers": [{"id": layer.id(), "name": layer.name()} for layer in layers],
        "items_created": created,
        "output_path": str(output_path) if output_path else "",
        "format": export_format,
        "export": export_result,
        "styling": styling,
        "notes": notes,
        "audit": audit,
    }


def _orientation_advice(
    extent: Any, frame: Any, page: PageSpec, template: str, *, gutter: float, **flags: bool
) -> list[str]:
    """Diz se girar a página renderia uma escala maior — e só quando renderia.

    A orientação decide quanto da folha o mapa aproveita: um estado mais alto
    que largo numa folha em paisagem desperdiça as laterais e sai numa escala
    menor do que poderia.

    A comparação não pode ser feita pela proporção da *página*: o solucionador
    põe coluna lateral numa orientação e faixa inferior na outra, então o quadro
    resultante não acompanha a folha. É preciso resolver o layout alternativo de
    verdade e comparar os quadros. Sem isso o conselho se inverte — a versão em
    retrato chegava a recomendar paisagem, que era pior.
    """
    if extent.height() <= 0 or frame.height <= 0:
        return []
    data_aspect = extent.width() / extent.height()

    def waste(frame_width: float, frame_height: float) -> float:
        if frame_height <= 0:
            return float("inf")
        frame_aspect = frame_width / frame_height
        return max(data_aspect / frame_aspect, frame_aspect / data_aspect)

    current = waste(frame.width, frame.height)
    if current < 1.35:
        return []

    flipped = "portrait" if page.orientation == "landscape" else "landscape"
    try:
        alternative = solve_layout(
            page=resolve_page(page.name, flipped),
            template=template,
            include_legend=flags.get("include_legend", True),
            include_scale_bar=flags.get("include_scale_bar", True),
            include_scale_text=flags.get("include_scale_text", True),
            include_north_arrow=flags.get("include_north", True),
            include_subtitle=flags.get("include_subtitle", True),
            include_logo=flags.get("include_logo", False),
            grid_annotation_gutter_mm=gutter,
        ).map_frame()
    except Exception:
        return []

    if waste(alternative.width, alternative.height) >= current * 0.9:
        return []

    # A escala é ditada pelo eixo mais apertado: terreno dividido por quadro.
    current_factor = max(extent.width() / frame.width, extent.height() / frame.height)
    alternative_factor = max(extent.width() / alternative.width, extent.height() / alternative.height)
    if alternative_factor <= 0:
        return []
    gain = current_factor / alternative_factor
    if gain < 1.12:  # abaixo disso o ganho não paga o ruído do aviso
        return []

    label = "retrato" if flipped == "portrait" else "paisagem"
    return [
        f"Os dados têm proporção {data_aspect:.2f} e o quadro {frame.width / frame.height:.2f}. "
        f"Em {label} o mapa caberia numa escala cerca de {gain:.1f}x maior, aproveitando melhor a folha."
    ]


def audit_layout(
    layout: Any,
    *,
    page: PageSpec | None = None,
    output_path: str | None = None,
    data_extent: dict[str, float] | None = None,
    map_frame: Rect | None = None,
) -> dict[str, Any]:
    """Observa um layout e roda o regulamento cartográfico contra ele."""
    from .inspector import measure_ink_fraction, observe_layout

    ink = None
    if output_path and str(output_path).lower().endswith(".png") and map_frame is not None and page is not None:
        ink = measure_ink_fraction(output_path, map_frame.to_dict(), (page.width_mm, page.height_mm))

    observation = observe_layout(
        layout,
        output_path=output_path,
        page_spec=page,
        data_extent=data_extent,
        ink_fraction=ink,
    )
    report = evaluate(observation)
    report["observation"] = observation
    return report


# ---------------------------------------------------------------------------
# Construção de itens
# ---------------------------------------------------------------------------

def _unique_layout_name(project: Any, title: str) -> str:
    import re

    base = re.sub(r"[^0-9A-Za-zÀ-ÿ _-]+", "", str(title)).strip() or "Mapa SIGMAI"
    name = base
    index = 2
    while project.layoutManager().layoutByName(name) is not None:
        name = f"{base} ({index})"
        index += 1
    return name


def _apply_page_size(layout: Any, page: PageSpec, imports: dict[str, Any]) -> None:
    mm = layout_unit_mm(imports["Qgis"], imports["QgsUnitTypes"])
    collection = layout.pageCollection()
    size = imports["QgsLayoutSize"](page.width_mm, page.height_mm, mm)
    if collection.pageCount() == 0:
        page_item = imports["QgsLayoutItemPage"](layout)
        page_item.setPageSize(size)
        collection.addPage(page_item)
    else:
        collection.page(0).setPageSize(size)


def _place(item: Any, rect: Rect, imports: dict[str, Any], mm: Any) -> None:
    item.attemptMove(imports["QgsLayoutPoint"](rect.x, rect.y, mm))
    item.attemptResize(imports["QgsLayoutSize"](rect.width, rect.height, mm))


def _add_label(
    layout: Any, item_id: str, text: str, rect: Rect, font_pt: float,
    imports: dict[str, Any], mm: Any, *, bold: bool = False, align: str = "left",
) -> Any:
    label = imports["QgsLayoutItemLabel"](layout)
    label.setId(item_id)
    label.setText(text)
    font = imports["QFont"]()
    font.setPointSizeF(float(font_pt))
    font.setBold(bool(bold))
    try:
        label.setFont(font)
    except Exception:
        pass
    # QGIS ≥3.24: a fonte efetiva vem do QgsTextFormat.
    try:
        text_format = label.textFormat()
        text_format.setFont(font)
        text_format.setSize(float(font_pt))
        text_format.setSizeUnit(qt_enum(imports["Qgis"], "RenderUnit", "Points"))
        label.setTextFormat(text_format)
    except Exception:
        pass
    try:
        horizontal = {"left": "AlignLeft", "center": "AlignHCenter", "right": "AlignRight"}[align]
        from qgis.PyQt.QtCore import Qt  # type: ignore

        label.setHAlign(qt_enum(Qt, "AlignmentFlag", horizontal))
        label.setVAlign(qt_enum(Qt, "AlignmentFlag", "AlignVCenter"))
    except Exception:
        pass
    layout.addLayoutItem(label)
    _place(label, rect, imports, mm)
    return label


def _add_legend(
    layout: Any, map_item: Any, layers: list[Any], plan: LayoutPlan,
    params: dict[str, Any], imports: dict[str, Any], mm: Any,
) -> Any:
    legend = imports["QgsLayoutItemLegend"](layout)
    legend.setId("legend")
    legend.setTitle(str(params.get("legend_title", "Legenda")))
    legend.setLinkedMap(map_item)
    layout.addLayoutItem(legend)

    # Modelo manual: garante que a legenda liste exatamente as camadas do
    # quadro. O modo automático herda a árvore do projeto, que quase nunca
    # coincide com o que o mapa desenha.
    try:
        legend.setAutoUpdateModel(False)
        root = legend.model().rootGroup()
        for node in list(root.children()):
            root.removeChildNode(node)
        for layer in layers:
            root.addLayer(layer)
        legend.updateLegend()
    except Exception:
        try:
            legend.setAutoUpdateModel(True)
            legend.setLegendFilterByMapEnabled(True)
        except Exception:
            pass

    slot = plan.slots["legend"]
    try:
        legend.setResizeToContents(False)
        # Colunas: uma coluna estreita com muitas entradas transborda a caixa.
        entries = max(1, len(layers))
        legend.setColumnCount(2 if (slot.aspect > 1.6 and entries > 3) else 1)
        legend.setSplitLayer(True)
        legend.setEqualColumnWidth(True)
    except Exception:
        pass
    try:
        font = imports["QFont"]()
        font.setPointSizeF(float(plan.fonts["legend"]))
        from qgis.core import QgsLegendStyle  # type: ignore

        for style_name in ("Title", "Group", "Subgroup", "SymbolLabel"):
            style = qt_enum(QgsLegendStyle, "Style", style_name)
            legend.setStyleFont(style, font)
    except Exception:
        pass
    _place(legend, slot, imports, mm)
    return legend


def _add_scalebar(layout: Any, map_item: Any, spec: Any, plan: LayoutPlan, imports: dict[str, Any], mm: Any, page: PageSpec | None = None) -> Any:
    bar = imports["QgsLayoutItemScaleBar"](layout)
    bar.setId("scale_bar")
    bar.setLinkedMap(map_item)
    layout.addLayoutItem(bar)
    try:
        bar.setStyle("Single Box")
    except Exception:
        pass
    unit_name = {"km": "Kilometers", "m": "Meters", "cm": "Centimeters"}.get(spec.unit, "Meters")
    try:
        bar.setUnits(distance_unit(imports["Qgis"], imports["QgsUnitTypes"], unit_name))
    except Exception:
        pass
    bar.setUnitLabel(spec.unit_label)
    bar.setUnitsPerSegment(float(spec.units_per_segment))
    bar.setNumberOfSegments(int(spec.segments_right))
    bar.setNumberOfSegmentsLeft(int(spec.segments_left))
    try:
        font = imports["QFont"]()
        font.setPointSizeF(max(6.0, float(plan.fonts["scale_text"]) - 1.0))
        text_format = bar.textFormat()
        text_format.setFont(font)
        text_format.setSize(max(6.0, float(plan.fonts["scale_text"]) - 1.0))
        text_format.setSizeUnit(qt_enum(imports["Qgis"], "RenderUnit", "Points"))
        bar.setTextFormat(text_format)
    except Exception:
        pass
    slot = plan.slots["scale_bar"]
    _place(bar, slot, imports, mm)
    try:
        bar.update()
        # O item de barra cresce para caber os rótulos. Se estourar a faixa
        # reservada, recua para a esquerda em vez de invadir a margem (CART041).
        actual = bar.sizeWithUnits()
        overflow = float(actual.width()) - slot.width
        if overflow > 0.1 and page is not None:
            # Se ainda assim transbordar, empurra para a ESQUERDA apenas até o
            # limite da área útil — nunca para dentro do quadro do mapa, que
            # fica à esquerda da faixa de apoio. Mover para lá trocava um aviso
            # de margem por uma sobreposição sobre o mapa, que é pior.
            right_edge = page.content_x_mm + page.content_width_mm
            new_x = min(slot.x, right_edge - float(actual.width()))
            new_x = max(new_x, slot.x - overflow)
            bar.attemptMove(imports["QgsLayoutPoint"](max(page.content_x_mm, new_x), slot.y, mm))
    except Exception:
        pass
    return bar


def _add_north_arrow(layout: Any, map_item: Any, rect: Rect, imports: dict[str, Any], mm: Any, notes: list[str]) -> str:
    svg_path = _find_north_arrow_svg(imports)
    if not svg_path:
        notes.append(
            "Nenhum SVG de norte foi encontrado na instalação do QGIS; usado rótulo de texto. "
            "Isso viola a regra CART025."
        )
        label = _add_label(layout, "north_arrow", "N", rect, 14.0, imports, mm, bold=True, align="center")
        return "label"

    picture = imports["QgsLayoutItemPicture"](layout)
    picture.setId("north_arrow")
    layout.addLayoutItem(picture)
    try:
        picture.setMode(qt_enum(imports["QgsLayoutItemPicture"], "Format", "FormatSVG"))
    except Exception:
        pass
    picture.setPicturePath(svg_path)
    try:
        # "Zoom" ajusta o desenho dentro do quadro reservado. "ZoomResizeFrame"
        # redimensiona o próprio item para a proporção do SVG, o que fazia a
        # rosa dos ventos crescer para fora da margem (CART041).
        picture.setResizeMode(qt_enum(imports["QgsLayoutItemPicture"], "ResizeMode", "Zoom"))
    except Exception:
        pass
    try:
        # Ligar ao mapa faz o símbolo girar junto com o norte da grade: é
        # exatamente o que um rótulo de texto não consegue fazer.
        picture.setLinkedMap(map_item)
        picture.setNorthMode(qt_enum(imports["QgsLayoutItemPicture"], "NorthMode", "GridNorth"))
    except Exception:
        notes.append("O QGIS não permitiu ligar a rosa dos ventos ao norte da grade nesta versão.")
    _place(picture, rect, imports, mm)
    return "picture"


def _apply_grid(map_item: Any, fitted: Any, map_crs: Any, plan: LayoutPlan, imports: dict[str, Any], notes: list[str], style: str = "solid") -> None:
    """Configura a grade de coordenadas de forma que ela realmente apareça.

    Três decisões separam esta implementação da anterior:

    1. o intervalo é calculado a partir da extensão — sem isso o QGIS usa 0.0 e
       não desenha nada, que era o comportamento do SIGMAI 0.1.1;
    2. os rótulos vão para **fora** do quadro; dentro, eles se sobrepõem às
       feições e são cortados pela moldura;
    3. os rótulos laterais são verticais, para que sete dígitos de coordenada
       UTM consumam a altura da linha e não onze milímetros de largura.
    """
    grid_class = imports["QgsLayoutItemMapGrid"]
    grid = map_item.grid()
    geographic = bool(map_crs.isGeographic())
    interval = max(
        graticule_interval(fitted.width, 4, geographic=geographic),
        graticule_interval(fitted.height, 3, geographic=geographic),
    )

    grid.setEnabled(True)
    _try(lambda: grid.setUnits(qt_enum(grid_class, "GridUnit", "MapUnit")))
    grid.setIntervalX(interval)
    grid.setIntervalY(interval)
    grid.setOffsetX(0.0)
    grid.setOffsetY(0.0)

    style_member = {"solid": "Solid", "cross": "Cross", "markers": "Markers", "frame": "FrameAnnotationsOnly"}.get(
        str(style).lower(), "Solid"
    )
    _try(lambda: grid.setStyle(qt_enum(grid_class, "GridStyle", style_member)))
    _try(lambda: grid.setGridLineColor(imports["QColor"](150, 150, 150, 130)))
    _try(lambda: grid.setGridLineWidth(0.08))

    _try(lambda: grid.setFrameStyle(qt_enum(grid_class, "FrameStyle", "Zebra")))
    _try(lambda: grid.setFrameWidth(0.9))
    _try(lambda: grid.setFramePenSize(0.15))

    grid.setAnnotationEnabled(True)
    font_pt = max(6.0, float(plan.fonts["footer"]) - 0.5)
    _try(lambda: grid.setAnnotationPrecision(3 if geographic else 0))
    _try(lambda: grid.setAnnotationFontColor(imports["QColor"]("#1E2A32")))
    _try(lambda: grid.setAnnotationFrameDistance(0.8))

    font = imports["QFont"]()
    font.setPointSizeF(font_pt)
    _try(lambda: grid.setAnnotationFont(font))
    def _apply_text_format() -> None:
        text_format = grid.annotationTextFormat()
        text_format.setFont(font)
        text_format.setSize(font_pt)
        text_format.setSizeUnit(qt_enum(imports["Qgis"], "RenderUnit", "Points"))
        grid.setAnnotationTextFormat(text_format)
    _try(_apply_text_format)

    outside = None
    try:
        outside = qt_enum(grid_class, "AnnotationPosition", "OutsideMapFrame")
    except Exception:
        pass
    horizontal = _quiet(lambda: qt_enum(grid_class, "AnnotationDirection", "Horizontal"))
    # "Vertical" lê de baixo para cima, que é a convenção das folhas
    # topográficas para os rótulos laterais; "VerticalDescending" inverte a
    # ordem dos dígitos aos olhos do leitor.
    vertical = _quiet(lambda: qt_enum(grid_class, "AnnotationDirection", "Vertical"))
    show_all = _quiet(lambda: qt_enum(grid_class, "DisplayMode", "ShowAll"))

    for side_name, direction in (("Left", vertical), ("Right", vertical), ("Top", horizontal), ("Bottom", horizontal)):
        side = _quiet(lambda name=side_name: qt_enum(grid_class, "BorderSide", name))
        if side is None:
            continue
        if outside is not None:
            _try(lambda s=side: grid.setAnnotationPosition(outside, s))
        if direction is not None:
            _try(lambda s=side, d=direction: grid.setAnnotationDirection(d, s))
        if show_all is not None:
            _try(lambda s=side: grid.setAnnotationDisplay(show_all, s))

    notes.append(
        f"Grade de coordenadas com intervalo de {interval:g} "
        f"{'grau(s)' if geographic else 'm'}, rótulos fora do quadro."
    )


def _try(action: Any) -> None:
    """Executa e engole a exceção: variações de API entre versões do QGIS."""
    try:
        action()
    except Exception:
        pass


def _quiet(action: Any) -> Any:
    try:
        return action()
    except Exception:
        return None


def _assert_render_thread(imports: dict[str, Any]) -> None:
    """Recusa renderizar fora da thread principal do Qt.

    O QGIS desenha layouts com QPainter, que só funciona na thread onde vive a
    aplicação. Numa thread de trabalho, ``exportToImage`` devolve *sucesso* e
    grava um PNG do tamanho certo com todos os pixels transparentes. Nenhum
    código de retorno acusa nada.

    A ponte normalmente evita isso enfileirando os comandos para a thread da
    interface do QGIS. Mas se a fila não estiver ativa — QTimer indisponível,
    QGIS iniciado de um jeito incomum — o comando cai no caminho direto e roda
    na thread do servidor HTTP. Melhor um erro explícito do que um mapa vazio
    com nota A.
    """
    try:
        from qgis.PyQt.QtCore import QCoreApplication, QThread  # type: ignore

        application = QCoreApplication.instance()
        if application is None:
            return
        if QThread.currentThread() is not application.thread():
            raise CompositionError(
                "A composição do mapa foi chamada fora da thread principal do QGIS, onde o Qt não "
                "desenha nada e a exportação sairia vazia sem acusar erro. Isso indica que a fila de "
                "comandos da ponte não está ativa; reinicie a ponte pelo painel do SIGMAI."
            )
    except ImportError:
        return


def _export(layout: Any, output_path: Path, export_format: str, params: dict[str, Any], imports: dict[str, Any]) -> dict[str, Any]:
    _assert_render_thread(imports)
    exporter = imports["QgsLayoutExporter"](layout)
    dpi = int(params.get("dpi", 300))
    if export_format == "png":
        settings = imports["QgsLayoutExporter"].ImageExportSettings()
        settings.dpi = dpi
        result = exporter.exportToImage(str(output_path), settings)
    elif export_format == "svg":
        settings = imports["QgsLayoutExporter"].SvgExportSettings()
        settings.dpi = dpi
        result = exporter.exportToSvg(str(output_path), settings)
    else:
        settings = imports["QgsLayoutExporter"].PdfExportSettings()
        settings.dpi = dpi
        result = exporter.exportToPdf(str(output_path), settings)
    # QgsLayoutExporter.Success vira QgsLayoutExporter.ExportResult.Success
    # no Qt6; sem a forma qualificada, toda exportação quebra no QGIS 4.
    success = result == qt_enum(imports["QgsLayoutExporter"], "ExportResult", "Success")
    return {
        "exported": bool(success),
        "result_code": int(result),
        "dpi": dpi,
        "path": str(output_path),
        "exists": output_path.exists(),
        "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
    }
