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
from .rulebook import SCALEBAR_MIN_LENGTH_MM, evaluate
from .scaling import (
    SCALEBAR_MIN_FRACTION,
    fit_extent_to_frame,
    graticule_interval,
    scalebar_spec,
)
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


#: Tudo que compose_map entende. Um parâmetro fora desta lista é recusado.
#:
#: Aceitar em silêncio o que não se entende é o pior comportamento possível
#: para um agente de IA: ele pede um inserto de localização, recebe um mapa sem
#: inserto e uma auditoria nota A, e não tem como saber que o pedido evaporou.
#: Recusar com a lista do que existe transforma o erro numa instrução.
KNOWN_PARAMETERS = frozenset({
    # camadas e assunto
    "layer_ids", "layers", "layer_id", "subject_layer_id",
    # texto
    "title", "subtitle", "legend_title", "data_source", "map_author",
    "map_author_email", "organization", "production_date", "notes_text",
    # página e template
    "page", "orientation", "margin_mm", "template", "layout_template", "layout_name",
    # geografia
    "map_crs", "auto_projected_crs", "margin_percent", "round_scale", "scale",
    # elementos
    "include_legend", "include_scale_bar", "include_scale_text", "include_north_arrow",
    "include_grid", "include_logo", "include_inset", "grid_style", "logo_path",
    # inserto de localização
    "inset_layer_ids", "inset_zoom_factor",
    # comparação lado a lado
    "second_map", "comparison_same_scale", "panel_title",
    # rótulos
    "label_field", "label_layer_id", "label_font_size",
    # estilo
    "apply_style", "style_profile",
    # saída
    "output_path", "format", "dpi", "confirm_overwrite",
})

# Formatos que QgsLayoutExporter sabe escrever nesta ferramenta.
SUPPORTED_FORMATS = frozenset({"png", "pdf", "svg"})


def _reject_unknown_parameters(params: dict[str, Any]) -> None:
    import difflib

    unknown = sorted(set(params) - KNOWN_PARAMETERS)
    if not unknown:
        return
    hints = []
    for name in unknown:
        close = difflib.get_close_matches(name, sorted(KNOWN_PARAMETERS), n=2, cutoff=0.6)
        hints.append(f"{name}" + (f" (você quis dizer {' ou '.join(close)}?)" if close else ""))
    raise CompositionError(
        "Parâmetros desconhecidos: " + "; ".join(hints) + ". "
        "compose_map não os ignora em silêncio para que você não receba um mapa diferente do pedido. "
        "Parâmetros aceitos: " + ", ".join(sorted(KNOWN_PARAMETERS)) + "."
    )


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
        # isEmpty() é verdadeiro para uma extensão de largura zero — o caso de
        # uma camada com um único ponto. Isso não é "sem extensão", é uma
        # extensão degenerada, e "mapa do meu ponto de coleta" é um pedido
        # legítimo. Só isNull() (tudo zero) significa ausência de posição.
        if rect is None or rect.isNull():
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
    if combined is None:
        empty = [layer.name() for layer in layers if layer.extent() is None or layer.extent().isEmpty()]
        raise CompositionError(
            "Nenhuma das camadas informadas tem extensão: " + ", ".join(empty or ["desconhecidas"]) + ". "
            "Camadas sem feições não podem definir o recorte do mapa; informe ao menos uma camada com dados."
        )

    # Uma camada com uma feição pontual — ou todas as feições no mesmo ponto —
    # tem extensão de largura zero. Recusar seria errado: "mapa do meu ponto de
    # coleta" é um pedido legítimo. O recorte é aberto em torno do ponto.
    if combined.width() <= 0 or combined.height() <= 0:
        centre_x = (combined.xMinimum() + combined.xMaximum()) / 2.0
        centre_y = (combined.yMinimum() + combined.yMaximum()) / 2.0
        geographic = bool(target_crs.isGeographic()) if target_crs is not None else False
        radius = 0.005 if geographic else 500.0  # ~500 m nos dois casos
        combined = imports["QgsRectangle"](
            centre_x - radius, centre_y - radius, centre_x + radius, centre_y + radius
        )
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


def _crs_identifier(crs: Any, label: str = "") -> str:
    """Identificação do CRS para quem lê a resposta.

    ``authid()`` devolve string vazia num CRS definido por parâmetros (a LAEA
    centrada nos dados, por exemplo). Devolver "" fazia o assistente relatar um
    mapa "sem CRS" quando o mapa estava, na verdade, corretamente projetado.
    """
    try:
        authid = str(crs.authid() or "").strip()
        if authid:
            return authid
        description = str(crs.description() or "").strip() or label.strip()
        if description:
            return f"{description} (sem código EPSG)"
        return "CRS personalizado (sem código EPSG)"
    except Exception:
        return ""


def _scalebar_needs_full_width(
    plan: LayoutPlan, fitted: Any, frame: Rect, include_scale_bar: bool, second_map_spec: Any
) -> bool:
    """A barra cabe legível na coluna lateral, ou precisa da largura do mapa?

    A escala só existe depois de ajustar a extensão ao quadro, e a largura da
    faixa só existe depois de resolver o layout: a checagem tem de vir entre as
    duas, e a correção é resolver o layout mais uma vez.
    """
    if not include_scale_bar or second_map_spec or plan.arrangement != "coluna_lateral":
        return False
    slot = plan.slots.get("scale_bar")
    if slot is None:
        return False
    overhang = max(10.0, plan.fonts["legend"] * 1.6)
    probe = scalebar_spec(
        fitted.scale_denominator, frame.width, max_width_mm=max(12.0, slot.width - overhang)
    )
    return (
        probe.bar_width_mm < SCALEBAR_MIN_LENGTH_MM
        and probe.frame_fraction < SCALEBAR_MIN_FRACTION
    )


def _aspect_expanded(extent: Any, frame_width: float, frame_height: float, imports: dict[str, Any]) -> Any:
    """A extensão que o quadro vai realmente exigir, já alargada para a proporção.

    ``fit_extent_to_frame`` alarga o recorte no eixo que sobra para casar com a
    razão do quadro. Escolher a projeção antes disso julgava a zona UTM pelo
    recorte dos dados e não pelo recorte impresso — um recorte alto e estreito
    passava no teste e depois aparecia no papel com quase 1.000 km de largura,
    com eastings de 1.262.000 numa zona que termina em 834.000.
    """
    if extent is None or frame_height <= 0 or frame_width <= 0:
        return extent
    frame_aspect = frame_width / frame_height
    width = max(extent.width(), 1e-12)
    height = max(extent.height(), 1e-12)
    if width / height < frame_aspect:
        new_width, new_height = height * frame_aspect, height
    else:
        new_width, new_height = width, width / frame_aspect
    centre_x = (extent.xMinimum() + extent.xMaximum()) / 2.0
    centre_y = (extent.yMinimum() + extent.yMaximum()) / 2.0
    return imports["QgsRectangle"](
        centre_x - new_width / 2.0, centre_y - new_height / 2.0,
        centre_x + new_width / 2.0, centre_y + new_height / 2.0,
    )


def _resolve_layer_ids(raw_ids: Any, imports: dict[str, Any], label: str) -> list[Any]:
    """Resolve identificadores ou nomes de camada, recusando os que não existem."""
    project = imports["QgsProject"].instance()
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    layers, missing = [], []
    for identifier in raw_ids or []:
        layer = project.mapLayer(str(identifier))
        if layer is None:
            matches = project.mapLayersByName(str(identifier))
            layer = matches[0] if matches else None
        if layer is None:
            missing.append(str(identifier))
        else:
            layers.append(layer)
    if missing:
        raise CompositionError(f"{label}: camadas não encontradas: {', '.join(missing)}.")
    return layers


def _subject_subset(layers: list[Any], subject: str) -> list[Any]:
    """As camadas que definem o recorte: a de assunto, se houver, senão todas."""
    subject = str(subject or "").strip()
    if not subject:
        return layers
    chosen = [layer for layer in layers if layer.id() == subject or layer.name() == subject]
    return chosen or layers


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
    _reject_unknown_parameters(params)
    imports = _imports()
    project = imports["QgsProject"].instance()

    layers = _resolve_layers(params, imports)
    styling = apply_default_symbology(layers, str(params.get("apply_style", "missing")))
    # ``strict=True``: se o assistente pediu um formato que não existe, é melhor
    # dizer isso do que devolver, em silêncio, uma folha A4 que ninguém pediu.
    try:
        page: PageSpec = resolve_page(
            params.get("page"), params.get("orientation"), params.get("margin_mm"),
            strict=params.get("page") is not None,
        )
    except ValueError as exc:
        raise CompositionError(str(exc)) from exc

    template = str(params.get("template", params.get("layout_template", DEFAULT_TEMPLATE)))
    if template not in TEMPLATES:
        import difflib

        near = difflib.get_close_matches(template, list(TEMPLATES), n=1, cutoff=0.5)
        suggestion = f" Você quis dizer '{near[0]}'?" if near else ""
        raise CompositionError(
            f"Template de layout desconhecido: '{template}'.{suggestion} "
            f"Templates disponíveis: {', '.join(sorted(TEMPLATES))}."
        )

    include_legend = bool(params.get("include_legend", True))
    include_scale_bar = bool(params.get("include_scale_bar", True))
    include_scale_text = bool(params.get("include_scale_text", True))
    include_north = bool(params.get("include_north_arrow", True))
    include_grid = bool(params.get("include_grid", True))
    include_subtitle = bool(str(params.get("subtitle", "")).strip())
    include_logo = bool(params.get("include_logo", False))
    include_inset = bool(params.get("include_inset", False))
    second_map_spec = params.get("second_map") or None
    if second_map_spec is not None and not isinstance(second_map_spec, dict):
        raise CompositionError("second_map precisa ser um objeto com layer_ids e, opcionalmente, panel_title.")

    # O corredor precisa caber o rótulo mais longo da grade. Coordenadas UTM
    # têm 7 dígitos; escritas na vertical nas laterais, consomem a altura da
    # linha, não a largura do texto.
    annotation_gutter = 0.0
    if include_grid:
        base_font = TEMPLATES.get(template, TEMPLATES[DEFAULT_TEMPLATE])["footer_font_pt"]
        annotation_gutter = max(5.0, float(base_font) * 0.62)

    layout_request = dict(
        page=page,
        template=template,
        include_legend=include_legend,
        include_scale_bar=include_scale_bar,
        include_scale_text=include_scale_text,
        include_north_arrow=include_north,
        include_subtitle=include_subtitle,
        include_logo=include_logo,
        include_inset=include_inset,
        grid_annotation_gutter_mm=annotation_gutter,
        panels=2 if second_map_spec else 1,
    )
    plan = solve_layout(**layout_request)
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
    map_crs_label = ""

    # Assunto e contexto são coisas diferentes. "Mapa do parque, mostrando os
    # municípios em volta" enquadra o parque e desenha os municípios; usar a
    # união de todas as camadas enquadraria o estado inteiro e o parque
    # sumiria. Sem isto, a única forma de obter um recorte de detalhe era
    # remover as camadas de contexto — e perder o contexto.
    subject_id = str(params.get("subject_layer_id", "")).strip()
    extent_layers = layers
    if subject_id:
        subject = [layer for layer in layers if layer.id() == subject_id or layer.name() == subject_id]
        if not subject:
            raise CompositionError(
                f"subject_layer_id não corresponde a nenhuma camada do mapa: {subject_id}. "
                "Camadas informadas: " + ", ".join(f"{layer.name()} ({layer.id()})" for layer in layers) + "."
            )
        extent_layers = subject
        notes.append(
            f"Recorte definido pela camada de assunto {subject[0].name()!r}; "
            "as demais entram como contexto."
        )

    extent = _combined_extent(extent_layers, map_crs, imports)

    if map_crs.isGeographic() and bool(params.get("auto_projected_crs", True)):
        # A projeção é escolhida pelo recorte que vai ao papel, não pelo recorte
        # cru dos dados: o quadro alarga a extensão para casar com sua proporção,
        # e um segundo painel pode cobrir uma área muito maior que o primeiro.
        decision_extent = _aspect_expanded(extent, frame.width, frame.height, imports)
        if second_map_spec is not None and "map_2" in plan.slots:
            second_layers = _resolve_layer_ids(
                second_map_spec.get("layer_ids") or second_map_spec.get("layers") or [],
                imports, "second_map",
            )
            if second_layers:
                second_extent = _combined_extent(
                    _subject_subset(second_layers, second_map_spec.get("subject_layer_id", "")),
                    map_crs, imports,
                )
                frame_2 = plan.slots["map_2"]
                decision_extent.combineExtentWith(
                    _aspect_expanded(second_extent, frame_2.width, frame_2.height, imports)
                )
        projected, label = _suggest_projected_crs(decision_extent, map_crs, imports)
        if projected is not None and label:
            map_crs = projected
            map_crs_label = label
            extent = _combined_extent(extent_layers, map_crs, imports)
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

    def _fit(target_frame: Rect) -> Any:
        return fit_extent_to_frame(
            extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum(),
            target_frame.width, target_frame.height,
            margin_percent=float(params.get("margin_percent", 5.0)),
            snap_to_round_scale=bool(params.get("round_scale", True)),
            map_units_per_metre=_map_units_per_metre(map_crs, extent, imports),
        )

    fitted = _fit(frame)

    # Segunda passada só quando a primeira revela que a barra não cabe legível
    # na coluna lateral. A escala só é conhecida depois do ajuste, então não há
    # como decidir isso antes de resolver o layout uma vez.
    if _scalebar_needs_full_width(plan, fitted, frame, include_scale_bar, second_map_spec):
        previous_notes = set(plan.notes)
        plan = solve_layout(**layout_request, scale_bar_under_map=True)
        frame = plan.map_frame()
        fitted = _fit(frame)
        notes.extend(note for note in plan.notes if note not in previous_notes)

    notes.extend(fitted.notes)

    if not include_inset:
        notes.extend(_locator_advice(extent, layers, extent_layers, map_crs, imports))

    notes.extend(
        _orientation_advice(
            extent, frame, page, template, gutter=annotation_gutter,
            include_legend=include_legend, include_scale_bar=include_scale_bar,
            include_scale_text=include_scale_text, include_north=include_north,
            include_subtitle=include_subtitle, include_logo=include_logo,
        )
    )

    # A comparação precisa ser resolvida aqui, e não ao final: se os painéis
    # forem igualados numa escala comum, é essa a escala que a barra e o texto
    # devem anunciar. Resolver depois de desenhá-los fazia o mapa dizer
    # 1:250.000 enquanto mostrava 1:5.000.000.
    comparison_plan = None
    if second_map_spec is not None and "map_2" in plan.slots:
        comparison_plan = _plan_comparison(second_map_spec, params, plan, map_crs, imports)
        if bool(params.get("comparison_same_scale", True)):
            shared = max(fitted.scale_denominator, comparison_plan["fitted"].scale_denominator)
            if shared != fitted.scale_denominator or shared != comparison_plan["fitted"].scale_denominator:
                notes.append(
                    f"Os dois painéis foram igualados em 1:{shared:,} — a escala mais aberta dos dois — "
                    "para que a comparação visual entre eles seja honesta.".replace(",", ".")
                )
            fitted = _rescale(fitted, shared)
            comparison_plan["fitted"] = _rescale(comparison_plan["fitted"], shared)
        else:
            # Escalas diferentes exigem que cada painel anuncie a sua. Uma barra
            # de escala única sob dois painéis desiguais afirma algo falso sobre
            # um deles.
            comparison_plan["per_panel_scale"] = True
            notes.append(
                f"Painéis em escalas diferentes (1:{fitted.scale_denominator:,} e "
                f"1:{comparison_plan['fitted'].scale_denominator:,}); cada painel anuncia a sua escala "
                "e a barra única foi substituída por essa indicação.".replace(",", ".")
            )

    layout_name = str(params.get("layout_name") or _unique_layout_name(project, params.get("title", "Mapa SIGMAI")))
    output_path = Path(str(params.get("output_path", ""))).expanduser() if params.get("output_path") else None
    export_format = str(params.get("format", (output_path.suffix.lstrip(".") if output_path else "pdf"))).lower()

    if context.get("dry_run"):
        return {
            "dry_run": True,
            "layout_name": layout_name,
            "plan": plan.to_dict(),
            "map_crs": _crs_identifier(map_crs, map_crs_label),
            "extent": fitted.to_dict(),
            "scale": _format_scale(fitted.scale_denominator),
            "layers": [{"id": layer.id(), "name": layer.name()} for layer in layers],
            "output_path": str(output_path) if output_path else "",
            "format": export_format,
            "notes": notes,
        }

    if output_path is not None:
        if output_path.is_dir():
            raise CompositionError(
                f"output_path é uma pasta, não um arquivo: {output_path}. "
                f"Inclua o nome do arquivo, por exemplo "
                f"{output_path / ('mapa.' + (export_format if export_format in SUPPORTED_FORMATS else 'png'))}."
            )
        if export_format not in SUPPORTED_FORMATS:
            suffix = output_path.suffix.lstrip(".")
            detail = (
                f"a extensão '.{suffix}' não é reconhecida"
                if suffix else "o caminho não tem extensão e nenhum format foi informado"
            )
            raise CompositionError(
                f"Formato de saída inválido: {detail}. "
                f"Use um destes: {', '.join(sorted(SUPPORTED_FORMATS))}."
            )
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
    # zoomToExtent e NÃO setExtent. A documentação do QGIS é explícita:
    # "setExtent ... may change the width or height of the map item to ensure
    # that the extent exactly matches". Ou seja, ele redimensiona o item e
    # desfaz o layout resolvido — o quadro do mapa vinha crescendo alguns
    # milímetros além da faixa calculada, e o inserto chegava a mais que dobrar
    # de altura e sair da página. Como a extensão já foi ajustada à razão de
    # aspecto do quadro, zoomToExtent não sobra nem falta.
    map_item.zoomToExtent(imports["QgsRectangle"](fitted.xmin, fitted.ymin, fitted.xmax, fitted.ymax))
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
    _verify_placement(map_item, frame, "main_map", notes)
    created["main_map"] = "map"

    if include_grid:
        _apply_grid(map_item, fitted, map_crs, plan, imports, notes, str(params.get("grid_style", "solid")))
        created["grid"] = "grid"

    # Rótulos das feições, quando pedidos
    label_field = str(params.get("label_field", "")).strip()
    if label_field:
        labelled = _apply_labels(layers, params, label_field, plan, imports, notes)
        if labelled:
            created["labels"] = labelled

    # Inserto de localização
    if include_inset and "inset" in plan.slots:
        _add_inset_map(layout, map_item, layers, plan, params, fitted, map_crs, imports, mm, notes)
        created["inset_map"] = "map"

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
    # O item do QGIS centra o último rótulo na extremidade da barra, então ela
    # transborda cerca de meia largura de rótulo de cada lado — uma folga em
    # milímetros, não uma fração. Descontar 30% da faixa punia justamente as
    # faixas largas, onde sobra espaço de sobra para os rótulos.
    label_overhang_mm = max(10.0, plan.fonts["legend"] * 1.6)
    bar_spec = scalebar_spec(
        fitted.scale_denominator,
        frame.width,
        max_width_mm=max(12.0, bar_slot_width - label_overhang_mm),
    )
    if include_scale_bar and "scale_bar" in plan.slots and not (comparison_plan or {}).get("per_panel_scale"):
        _add_scalebar(layout, map_item, bar_spec, plan, imports, mm, page)
        created["scale_bar"] = "scalebar"

    # Escala numérica
    if include_scale_text and "scale_text" in plan.slots:
        scale_caption = (
            "Escalas indicadas em cada painel"
            if (comparison_plan or {}).get("per_panel_scale")
            else f"Escala {_format_scale(fitted.scale_denominator)}"
        )
        _add_label(
            layout, "scale_text", scale_caption,
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

    # Segundo quadro de comparação
    if comparison_plan is not None:
        comparison_plan["main_scale"] = fitted.scale_denominator
        _build_comparison_map(layout, comparison_plan, params, plan, map_crs, imports, mm, notes)
        created["comparison_map"] = "map"
        created["panel_captions"] = "label"

    layout.refresh()
    try:
        map_item.refresh()
    except Exception:
        pass

    # --- exportação -------------------------------------------------------
    export_result: dict[str, Any] = {"exported": False}
    if output_path is not None:
        export_result = _export(layout, output_path, export_format, params, imports)
        # O exportador do QGIS pode devolver Success sem escrever nada (caminho
        # inválido, disco cheio, driver recusando). Falhar aqui, com o código de
        # retorno, é mais útil do que entregar um mapa que não existe.
        if not export_result.get("exists") or int(export_result.get("size_bytes", 0)) <= 0:
            raise CompositionError(
                f"A exportação não gerou o arquivo {output_path} "
                f"(código do QgsLayoutExporter: {export_result.get('result_code')}). "
                "Verifique o caminho, a extensão e a permissão de escrita na pasta."
            )

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
        "map_crs": _crs_identifier(map_crs, map_crs_label),
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


def _locator_advice(
    extent: Any, layers: list[Any], extent_layers: list[Any], map_crs: Any, imports: dict[str, Any]
) -> list[str]:
    """Sugere um inserto quando o recorte é pequeno diante do contexto.

    Quem não conhece a região faz duas perguntas, e "onde fica" vem antes de
    "como é". Um mapa de trilha a 1:25.000 responde só a segunda. O motor não
    acrescenta o inserto sozinho — ele muda a composição e pode não ser o que se
    quer — mas diz que ele caberia.
    """
    try:
        widest = None
        for layer in layers:
            rect = _layer_extent_in_crs(layer, map_crs, imports)
            if rect is None or rect.isEmpty():
                continue
            if widest is None or rect.width() > widest.width():
                widest = rect
        if widest is None or extent.width() <= 0:
            return []
        ratio = widest.width() / extent.width()
    except Exception:
        return []

    if ratio < 6.0:
        return []
    return [
        f"O recorte é cerca de {ratio:.0f}x menor que a camada mais ampla do mapa. "
        "Um inserto de localização ajudaria quem não conhece a região: passe include_inset=true."
    ]


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


def _verify_placement(item: Any, rect: Rect, label: str, notes: list[str], tolerance: float = 0.6) -> None:
    """Confere que o item ficou do tamanho da faixa que lhe foi reservada.

    Vários métodos do QGIS redimensionam o item como efeito colateral. Sem esta
    conferência, o layout resolvido é uma intenção, não uma garantia.
    """
    try:
        size = item.sizeWithUnits()
        position = item.positionWithUnits()
    except Exception:
        return
    drift = max(
        abs(float(size.width()) - rect.width),
        abs(float(size.height()) - rect.height),
        abs(float(position.x()) - rect.x),
        abs(float(position.y()) - rect.y),
    )
    if drift > tolerance:
        notes.append(
            f"O item {label!r} saiu do lugar reservado: pedido "
            f"{rect.width:.1f}x{rect.height:.1f} mm em ({rect.x:.1f}, {rect.y:.1f}), "
            f"obtido {float(size.width()):.1f}x{float(size.height()):.1f} mm em "
            f"({float(position.x()):.1f}, {float(position.y()):.1f})."
        )


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


def _apply_labels(
    layers: list[Any], params: dict[str, Any], field: str, plan: LayoutPlan,
    imports: dict[str, Any], notes: list[str],
) -> str:
    """Rotula as feições de uma camada pelo campo pedido.

    Um mapa de trilha sem o nome da trilha, ou de municípios sem os nomes, é
    metade de um mapa. Antes era preciso uma segunda chamada a create_labels e
    saber que ela existia; o compositor agora resolve na mesma passada.
    """
    from qgis.core import (  # type: ignore
        QgsPalLayerSettings,
        QgsTextBufferSettings,
        QgsTextFormat,
        QgsVectorLayerSimpleLabeling,
    )

    import difflib

    requested_id = str(params.get("label_layer_id", "")).strip()
    vector_layers = [layer for layer in layers if hasattr(layer, "fields")]

    if requested_id and requested_id not in [layer.id() for layer in layers]:
        known = ", ".join(f"{layer.name()} ({layer.id()})" for layer in layers)
        raise CompositionError(
            f"label_layer_id não está entre as camadas do mapa: {requested_id!r}. "
            f"Camadas do mapa: {known}."
        )

    candidates = [
        layer for layer in vector_layers
        if not requested_id or layer.id() == requested_id
    ]
    target = None
    for layer in candidates:
        if field in [item.name() for item in layer.fields()]:
            target = layer
            break

    if target is None:
        # Rotular era um pedido explícito. Devolver o mapa sem rótulos e só
        # anotar isso entrega ao usuário um mapa diferente do que o assistente
        # descreveu; recusar com a lista de campos deixa a correção óbvia.
        available = {
            layer.name(): [item.name() for item in layer.fields()]
            for layer in (candidates or vector_layers)
        }
        todos = sorted({name for campos in available.values() for name in campos})
        near = difflib.get_close_matches(field, todos, n=2, cutoff=0.6)
        suggestion = f" Você quis dizer {' ou '.join(repr(n) for n in near)}?" if near else ""
        detalhe = "; ".join(f"{nome}: {', '.join(campos) or '(sem campos)'}" for nome, campos in available.items())
        raise CompositionError(
            f"O campo de rótulo {field!r} não existe nas camadas do mapa.{suggestion} "
            f"Campos disponíveis por camada — {detalhe}. "
            "Passe label_field com um destes nomes, ou omita label_field para não rotular."
        )

    settings = QgsPalLayerSettings()
    settings.fieldName = field
    settings.enabled = True
    try:
        # Linha rotulada acompanha o traçado; polígono e ponto ficam melhor com
        # rótulo horizontal ao redor do centroide.
        geometry = _geometry_name(target, imports)
        placement = qt_enum(QgsPalLayerSettings, "Placement", "Curved" if geometry == "Line" else "AroundPoint")
        settings.placement = placement
    except Exception:
        pass

    text_format = QgsTextFormat()
    font = imports["QFont"]()
    font.setPointSizeF(float(params.get("label_font_size", plan.fonts["legend"])))
    text_format.setFont(font)
    text_format.setSize(float(params.get("label_font_size", plan.fonts["legend"])))
    try:
        text_format.setSizeUnit(qt_enum(imports["Qgis"], "RenderUnit", "Points"))
    except Exception:
        pass
    # Halo branco: sem ele o rótulo some sobre feições escuras e o mapa fica
    # ilegível justamente onde há mais informação.
    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(0.9)
    buffer_settings.setColor(imports["QColor"](255, 255, 255, 220))
    text_format.setBuffer(buffer_settings)
    settings.setFormat(text_format)

    target.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    target.setLabelsEnabled(True)
    target.triggerRepaint()
    notes.append(f"Feições de {target.name()!r} rotuladas pelo campo {field!r}.")
    return target.name()


def _geometry_name(layer: Any, imports: dict[str, Any]) -> str:
    try:
        from qgis.core import QgsWkbTypes  # type: ignore

        from .qtcompat import geometry_type

        value = layer.geometryType()
        for name in ("Point", "Line", "Polygon"):
            if value == geometry_type(imports["Qgis"], QgsWkbTypes, name):
                return name
    except Exception:
        pass
    return "unknown"


def _plan_comparison(
    spec: dict[str, Any], params: dict[str, Any], plan: LayoutPlan, map_crs: Any, imports: dict[str, Any]
) -> dict[str, Any]:
    """Resolve camadas e recorte do segundo painel, sem ainda desenhar nada."""
    layers = _resolve_layer_ids(
        spec.get("layer_ids") or spec.get("layers") or [], imports, "second_map"
    )
    if not layers:
        raise CompositionError("second_map precisa de layer_ids com ao menos uma camada.")

    extent_layers = _subject_subset(layers, spec.get("subject_layer_id", ""))

    frame = plan.slots["map_2"]
    extent = _combined_extent(extent_layers, map_crs, imports)
    fitted = fit_extent_to_frame(
        extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum(),
        frame.width, frame.height,
        margin_percent=float(spec.get("margin_percent", params.get("margin_percent", 5.0))),
        snap_to_round_scale=bool(params.get("round_scale", True)),
        map_units_per_metre=_map_units_per_metre(map_crs, extent, imports),
    )
    return {"layers": layers, "fitted": fitted, "frame": frame, "spec": spec}


def _rescale(fitted: Any, scale: int) -> Any:
    """Mesma extensão, centrada, aberta ou fechada até a escala pedida."""
    growth = scale / max(1.0, float(fitted.scale_denominator))
    centre_x = (fitted.xmin + fitted.xmax) / 2.0
    centre_y = (fitted.ymin + fitted.ymax) / 2.0
    half_width = (fitted.xmax - fitted.xmin) * growth / 2.0
    half_height = (fitted.ymax - fitted.ymin) * growth / 2.0
    return replace(
        fitted,
        xmin=centre_x - half_width, xmax=centre_x + half_width,
        ymin=centre_y - half_height, ymax=centre_y + half_height,
        scale_denominator=int(scale),
    )


def _build_comparison_map(
    layout: Any, comparison: dict[str, Any], params: dict[str, Any], plan: LayoutPlan,
    map_crs: Any, imports: dict[str, Any], mm: Any, notes: list[str],
) -> Any:
    """Desenha o segundo quadro e as legendas de painel.

    A regra que sustenta o par é a escala: dois painéis em escalas diferentes
    convidam a uma comparação visual que não se sustenta, porque o mesmo
    tamanho no papel passa a significar tamanhos distintos no terreno. Por isso
    o padrão é igualar — e, quando não se iguala, dizer isso no laudo.
    """
    frame = comparison["frame"]
    fitted = comparison["fitted"]
    second = imports["QgsLayoutItemMap"](layout)
    second.setId("comparison_map")
    layout.addLayoutItem(second)
    _place(second, frame, imports, mm)
    second.setCrs(map_crs)
    second.setLayers(comparison["layers"])
    second.zoomToExtent(imports["QgsRectangle"](fitted.xmin, fitted.ymin, fitted.xmax, fitted.ymax))
    second.setFrameEnabled(True)
    _apply_grid(second, fitted, map_crs, plan, imports, [], str(params.get("grid_style", "solid")))
    _verify_placement(second, frame, "comparison_map", notes)

    left = str(params.get("panel_title", "")).strip() or str(params.get("title", "")).strip() or "Painel A"
    right = str(comparison["spec"].get("panel_title", "")).strip() or "Painel B"
    if comparison.get("per_panel_scale"):
        left = f"{left} — {_format_scale(comparison['main_scale'])}"
        right = f"{right} — {_format_scale(fitted.scale_denominator)}"
    for slot_name, item_id, text in (
        ("map_caption", "panel_caption_a", left),
        ("map_2_caption", "panel_caption_b", right),
    ):
        if slot_name in plan.slots:
            _add_label(layout, item_id, text, plan.slots[slot_name], plan.fonts["subtitle"],
                       imports, mm, bold=True, align="center")

    second.refresh()
    return second


def _zoom_to_scale(map_item: Any, fitted: Any, scale: int, imports: dict[str, Any]) -> None:
    """Centraliza o recorte e fixa a escala pedida, sem redimensionar o item."""
    centre_x = (fitted.xmin + fitted.xmax) / 2.0
    centre_y = (fitted.ymin + fitted.ymax) / 2.0
    growth = scale / max(1.0, float(fitted.scale_denominator))
    half_width = (fitted.xmax - fitted.xmin) * growth / 2.0
    half_height = (fitted.ymax - fitted.ymin) * growth / 2.0
    map_item.zoomToExtent(imports["QgsRectangle"](
        centre_x - half_width, centre_y - half_height, centre_x + half_width, centre_y + half_height
    ))


def _add_inset_map(
    layout: Any, main_map: Any, layers: list[Any], plan: LayoutPlan, params: dict[str, Any],
    fitted: Any, map_crs: Any, imports: dict[str, Any], mm: Any, notes: list[str],
) -> Any:
    """Mapa de localização, com o recorte principal desenhado por cima.

    É o elemento que mais falta num mapa de escala grande. Um mapa de trilha a
    1:25.000 responde "como é o lugar" e não responde "onde fica" — e para quem
    não conhece a região, a segunda pergunta vem primeiro. O QGIS resolve isso
    com um item de visão geral ligado ao mapa principal, que desenha
    automaticamente o retângulo do recorte e o mantém sincronizado.
    """
    slot = plan.slots["inset"]
    inset = imports["QgsLayoutItemMap"](layout)
    inset.setId("inset_map")
    layout.addLayoutItem(inset)
    _place(inset, slot, imports, mm)
    inset.setCrs(map_crs)

    requested = params.get("inset_layer_ids")
    inset_layers = layers
    if requested:
        project = imports["QgsProject"].instance()
        resolved = [project.mapLayer(str(item)) for item in requested]
        resolved = [item for item in resolved if item is not None]
        if resolved:
            inset_layers = resolved
        else:
            notes.append("Nenhuma das camadas de inset_layer_ids foi encontrada; o inserto usa as mesmas camadas do mapa.")
    inset.setLayers(inset_layers)

    # Os rótulos são propriedade da camada, então o inserto herdaria todos os
    # rótulos do mapa principal — dezenas de nomes de município empilhados numa
    # caixa de 4 cm. Um localizador precisa ser limpo: aqui cada camada recebe
    # um estilo sobreposto sem rotulagem, válido só para este item de mapa.
    overrides = _labelless_style_overrides(inset_layers)
    if overrides:
        try:
            # setKeepLayerStyles é o que faz o item respeitar as sobreposições;
            # sem ele o QGIS as ignora em silêncio e o inserto continua
            # carregando os rótulos do mapa principal.
            inset.setLayerStyleOverrides(overrides)
            inset.setKeepLayerStyles(True)
        except Exception as exc:
            notes.append(f"Não foi possível desligar os rótulos no inserto: {exc}")

    # O inserto precisa mostrar contexto: por padrão, uma área doze vezes mais
    # larga que o recorte principal, ajustada à proporção da caixa reservada.
    factor = max(2.0, float(params.get("inset_zoom_factor", 12.0)))
    centre_x = (fitted.xmin + fitted.xmax) / 2.0
    centre_y = (fitted.ymin + fitted.ymax) / 2.0
    half_width = (fitted.xmax - fitted.xmin) * factor / 2.0
    half_height = half_width / (slot.width / slot.height if slot.height else 1.0)
    context = imports["QgsRectangle"](
        centre_x - half_width, centre_y - half_height, centre_x + half_width, centre_y + half_height
    )

    # Se houver camada de contexto maior que essa janela, respeita a extensão
    # dela: mostrar o estado inteiro localiza melhor do que um quadrado vazio.
    widest = None
    for layer in inset_layers:
        try:
            extent = _layer_extent_in_crs(layer, map_crs, imports)
        except Exception:
            continue
        if extent is None or extent.isEmpty():
            continue
        if widest is None or extent.width() > widest.width():
            widest = extent
    # Havendo camada de contexto, o inserto mostra a extensão INTEIRA dela: um
    # localizador que corta o estado ao meio não localiza. O múltiplo do
    # recorte só vale quando não há contexto.
    if widest is not None and widest.width() > fitted.width * 1.5:
        context = imports["QgsRectangle"](widest)
        context.grow(max(context.width(), context.height()) * 0.04)

    inset.zoomToExtent(context)
    inset.setFrameEnabled(True)
    try:
        inset.setBackgroundColor(imports["QColor"](255, 255, 255))
    except Exception:
        pass

    # O retângulo do recorte principal desenhado sobre o inserto é o que liga
    # as duas escalas; sem ele o inserto é só um segundo mapa solto.
    try:
        from qgis.core import QgsFillSymbol, QgsLayoutItemMapOverview  # type: ignore

        overview = QgsLayoutItemMapOverview("recorte principal", inset)
        overview.setLinkedMap(main_map)
        overview.setEnabled(True)
        symbol = QgsFillSymbol.createSimple({
            "color": "255,255,255,0", "outline_color": "#C0392B", "outline_width": "0.5",
        })
        overview.setFrameSymbol(symbol)
        inset.overviews().addOverview(overview)
    except Exception as exc:
        notes.append(f"O retângulo de localização não pôde ser desenhado sobre o inserto: {exc}")

    inset.refresh()
    _verify_placement(inset, slot, "inset_map", notes)
    notes.append(
        f"Inserto de localização com {factor:g}x a largura do recorte principal, "
        "com o retângulo do recorte desenhado por cima."
    )

    # Um localizador que mostra só o próprio assunto ampliado não localiza
    # nada: precisa de uma feição de referência que o leitor reconheça.
    if widest is None or widest.width() <= fitted.width * 2.0:
        notes.append(
            "O inserto não tem camada de contexto mais ampla que o recorte, então mostra apenas o "
            "assunto sobre fundo vazio. Passe inset_layer_ids com um limite municipal, estadual ou "
            "de bacia para que ele de fato localize."
        )
    return inset


def _labelless_style_overrides(layers: list[Any]) -> dict[str, str]:
    """Estilo completo de cada camada, com a rotulagem removida.

    Exporta TODAS as categorias e depois retira o nó de rotulagem, em vez de
    exportar só as categorias de simbologia: um QML parcial faz o QGIS cair no
    renderizador padrão, e o inserto aparecia com uma cor diferente da do mapa
    principal. O leitor precisa reconhecer a mesma camada nos dois lugares.
    """
    from qgis.PyQt.QtXml import QDomDocument  # type: ignore

    overrides: dict[str, str] = {}
    for layer in layers:
        if not hasattr(layer, "labelsEnabled"):
            continue
        try:
            if not layer.labelsEnabled():
                continue
            document = QDomDocument()
            layer.exportNamedStyle(document)
            root = document.documentElement()
            root.setAttribute("labelsEnabled", "0")
            for tag in ("labeling", "labelling"):
                nodes = root.elementsByTagName(tag)
                while nodes.count():
                    root.removeChild(nodes.at(0))
            overrides[layer.id()] = document.toString()
        except Exception:
            continue
    return overrides


def _layer_extent_in_crs(layer: Any, target_crs: Any, imports: dict[str, Any]) -> Any:
    rect = layer.extent()
    if rect is None or rect.isEmpty():
        return None
    source_crs = layer.crs()
    if source_crs.isValid() and target_crs.isValid() and source_crs.authid() != target_crs.authid():
        transform = imports["QgsCoordinateTransform"](source_crs, target_crs, imports["QgsProject"].instance())
        return transform.transformBoundingBox(rect)
    return rect


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

    if geographic:
        interval_text = f"{interval:g} grau(s)"
    elif interval >= 1000:
        interval_text = f"{interval / 1000:,.10g} km".replace(",", ".")
    else:
        interval_text = f"{interval:,.10g} m".replace(",", ".")
    notes.append(
        f"Grade de coordenadas com intervalo de {interval_text}, rótulos fora do quadro."
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
