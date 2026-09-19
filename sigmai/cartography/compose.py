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
import math
import os
import platform
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from .layoutgrid import DEFAULT_TEMPLATE, TEMPLATES, LayoutPlan, Rect, solve_layout
from .maptext import MAP_TEXT, RTL_LANGUAGES, maptext, resolve_language
from .pagespec import PAGE_SIZES, PageSpec, resolve_page
from .params import ParameterError, as_flag, as_id_list, as_number, as_text
from .qtcompat import distance_unit, layout_unit_mm, qt_enum
from ..security import classify_output_path
from .rulebook import SCALEBAR_MIN_LENGTH_MM, evaluate
from .scaling import (
    SCALEBAR_MIN_FRACTION,
    fit_extent_to_frame,
    graticule_interval,
    scalebar_spec,
)
from .symbology import apply_default_symbology
from .textfit import MIN_FONT_PT, TextTooLongError, fit_text

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
    # língua dos textos que o compositor escreve sozinho na moldura (título
    # padrão, "Fonte:"/"Elaboração:", "Legenda", "Painel A/B", crédito da
    # ferramenta) — ver maptext.py. Não afeta title/subtitle/legend_title e
    # companhia, que já saem na língua em que o usuário os escreveu.
    "map_language",
    # página e template
    "page", "orientation", "margin_mm", "template", "layout_template", "layout_name", "arrangement",
    # geografia
    "map_crs", "auto_projected_crs", "margin_percent", "round_scale", "scale",
    # elementos
    "include_legend", "include_scale_bar", "include_scale_text", "include_north_arrow",
    "include_grid", "include_logo", "include_inset", "grid_style", "logo_path",
    # inserto de localização
    "inset_layer_ids", "inset_zoom_factor",
    # comparação lado a lado (2 painéis) e figura com N painéis (a), (b), (c)…
    "second_map", "comparison_same_scale", "panel_title", "panels",
    # figura para periódico: largura final impressa decide a página
    "figure_width_mm", "figure_height_mm", "figure_max_height_mm", "journal_column",
    # rótulos
    "label_field", "label_layer_id", "label_font_size",
    # estilo
    "apply_style",
    # saída
    "output_path", "format", "dpi", "confirm_overwrite",
    # receita reproduzível: JSON gravado ao lado (a receita vai sempre para o
    # layout e para os metadados do PNG; este é o arquivo avulso, opcional)
    "recipe_path",
})

# Formatos que QgsLayoutExporter sabe escrever nesta ferramenta.
SUPPORTED_FORMATS = frozenset({"png", "pdf", "svg", "tif", "tiff", "jpg", "jpeg"})

#: Larguras usuais de coluna em periódicos científicos (mm). Cada revista
#: tem a sua — a instrução aos autores manda; ``figure_width_mm`` vence.
JOURNAL_COLUMNS: dict[str, float] = {"single": 85.0, "one_and_half": 120.0, "double": 175.0}
FIGURE_DEFAULT_MAX_HEIGHT_MM = 230.0
FIGURE_MARGIN_MM = 2.0

#: Estilos de grade aceitos por ``grid_style`` — as chaves que ``_apply_grid``
#: sabe traduzir para o QGIS. Um valor fora daqui caía num padrão ("solid")
#: em silêncio; ver ``_apply_grid``.
GRID_STYLES: tuple[str, ...] = ("solid", "cross", "markers", "frame")

#: Regras do regulamento (rulebook.py) que significam "a exportação não
#: existe de verdade": quadro em branco (CART062) ou arquivo não gravado/vazio
#: demais (CART063). compose_map não pode devolver sucesso quando a própria
#: auditoria marca uma destas como erro — ver o bloco após ``audit_layout``.
_BLANK_OUTPUT_RULES = frozenset({"CART062", "CART063"})

#: Parâmetros que já foram cogitados e nunca chegaram a ter implementação —
#: ficavam em KNOWN_PARAMETERS e eram aceitos e ignorados em silêncio, o
#: mesmo defeito que a lista de conhecidos existe para evitar. Removidos daqui
#: para fora de KNOWN_PARAMETERS, caem na recusa de parâmetro desconhecido;
#: esta lista só troca a mensagem genérica por uma que explica o motivo.
_RETIRED_PARAMETER_HINTS: dict[str, str] = {
    "scale": (
        "não existe controle direto de escala nesta versão; a escala é derivada da extensão "
        "das camadas e de margin_percent/round_scale — ajuste esses dois para chegar perto do "
        "denominador que você quer."
    ),
    "style_profile": (
        "não existem perfis de estilo predefinidos; use apply_style ('missing', 'all' ou 'none') "
        "para controlar a reestilização automática, que aplica a paleta segura para daltônicos."
    ),
}


def _reject_unknown_parameters(params: dict[str, Any]) -> None:
    import difflib

    unknown = sorted(set(params) - KNOWN_PARAMETERS)
    if not unknown:
        return
    hints = []
    for name in unknown:
        if name in _RETIRED_PARAMETER_HINTS:
            hints.append(f"{name} ({_RETIRED_PARAMETER_HINTS[name]})")
            continue
        close = difflib.get_close_matches(name, sorted(KNOWN_PARAMETERS), n=2, cutoff=0.6)
        hints.append(f"{name}" + (f" (você quis dizer {' ou '.join(close)}?)" if close else ""))
    raise CompositionError(
        "Parâmetros desconhecidos: " + "; ".join(hints) + ". "
        "compose_map não os ignora em silêncio para que você não receba um mapa diferente do pedido. "
        "Parâmetros aceitos: " + ", ".join(sorted(KNOWN_PARAMETERS)) + "."
    )


def _resolve_template(params: dict[str, Any]) -> str:
    """Resolve ``template``/``layout_template`` para uma chave de TEMPLATES.

    Normaliza a caixa antes de comparar: ``"CIENTIFICO"`` era recusado
    enquanto ``page`` já tolerava ``"a4 LANDSCAPE"`` — a mesma tolerância que
    ``resolve_page`` aplica a page/orientation faltava aqui. A recusa para um
    nome de fato inexistente continua valendo, com sugestão por proximidade.
    Função pura (não toca QGIS) para poder ser testada sem PyQGIS.
    """
    template_raw = as_text(params, "template", default="", label="template")
    if not template_raw:
        template_raw = as_text(params, "layout_template", default="", label="layout_template")
    template_raw = template_raw or DEFAULT_TEMPLATE
    template = template_raw.strip().lower()
    if template not in TEMPLATES:
        import difflib

        near = difflib.get_close_matches(template, list(TEMPLATES), n=1, cutoff=0.5)
        suggestion = f" Você quis dizer '{near[0]}'?" if near else ""
        raise CompositionError(
            f"Template de layout desconhecido: '{template_raw}'.{suggestion} "
            f"Templates disponíveis: {', '.join(sorted(TEMPLATES))}."
        )
    return template


def _resolve_grid_style(params: dict[str, Any]) -> str:
    """Resolve ``grid_style`` para um dos valores que ``_apply_grid`` entende.

    Um valor fora de ``GRID_STYLES`` caía num padrão ("solid") em silêncio;
    aqui é recusado com a lista de aceitos e sugestão por proximidade. Função
    pura para poder ser testada sem PyQGIS.
    """
    grid_style_raw = as_text(params, "grid_style", default="solid", label="grid_style").strip()
    grid_style = grid_style_raw.lower()
    if grid_style not in GRID_STYLES:
        import difflib

        near = difflib.get_close_matches(grid_style, GRID_STYLES, n=1, cutoff=0.4)
        suggestion = f" Você quis dizer '{near[0]}'?" if near else ""
        raise CompositionError(
            f"grid_style desconhecido: {grid_style_raw!r}.{suggestion} "
            f"Valores aceitos: {', '.join(GRID_STYLES)}."
        )
    return grid_style


def _resolve_map_crs_text(params: dict[str, Any]) -> str:
    """Texto de ``map_crs`` pronto para ``QgsCoordinateReferenceSystem``.

    ``None``/chave ausente viram ``""`` (equivalente a omitir — antes disso
    ``map_crs: null`` era tratado como a string literal ``"None"`` e recusado
    com uma mensagem que não dizia por quê). Espaços em volta dos dois-pontos
    (``"EPSG: 4674"``, comum quando a IA copia texto em alemão) são
    normalizados: ``QgsCoordinateReferenceSystem`` não tolera esse espaço e
    recusava sem nenhuma dica de formato. Função pura para poder ser testada
    sem PyQGIS — a validação de que o resultado é um CRS de verdade continua
    em ``_compose_map``, que precisa do PyQGIS para isso.
    """
    raw = as_text(params, "map_crs", default="", label="map_crs").strip()
    if not raw:
        return ""
    return re.sub(r"\s*:\s*", ":", raw)


def _imports() -> dict[str, Any]:
    try:
        from qgis.PyQt.QtGui import QColor, QFont  # type: ignore
        from qgis.core import (  # type: ignore
            Qgis,
            QgsApplication,
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsDistanceArea,
            QgsFeatureRequest,
            QgsLayoutExporter,
            QgsLayoutItemLabel,
            QgsLayoutItemLegend,
            QgsLayoutItemMap,
            QgsLayoutItemMapGrid,
            QgsLayoutItemPage,
            QgsLayoutItemPicture,
            QgsLayoutItemScaleBar,
            QgsLayoutPoint,
            QgsLayoutUtils,
            QgsPointXY,
            QgsLayoutSize,
            QgsPrintLayout,
            QgsProject,
            QgsRectangle,
            QgsTextFormat,
            QgsTextRenderer,
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
    # As três chaves são sinônimos históricos; a primeira presente e válida
    # vence. as_id_list recusa o que não é iterável de textos (int, bool,
    # None, dict) em vez de deixar a iteração seguinte estourar TypeError.
    raw = None
    for key in ("layer_ids", "layers", "layer_id"):
        candidate = as_id_list(params, key, allow_single=True, label=key)
        if candidate:
            raw = candidate
            break
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
#: Ganho mínimo de escala (razão entre os fatores de ajuste) para trocar a
#: orientação da página ou o arranjo dos itens de apoio. Abaixo disso a troca
#: não paga a mudança de leitura da folha. Parâmetro declarado, não medido:
#: tools/threshold_sensitivity.py mostra em que faixa a decisão é estável.
LAYOUT_SWITCH_GAIN = 1.12

UTM_MAX_LONGITUDE_SPAN_DEGREES = 4.5
UTM_MAX_LATITUDE_SPAN_DEGREES = 12.0
REGIONAL_MAX_SPAN_DEGREES = 40.0

#: Caixa aproximada do território brasileiro, para escolher a Policônica.
#: Área de uso oficial do EPSG:5880 (SIRGAS 2000 / Policônica do Brasil) no
#: registro EPSG: oeste −74,01°, sul −35,71°, leste −25,28°, norte 7,04°.
#: A caixa anterior (−74, −34, −34, 6) parava no litoral continental e deixava
#: de fora Fernando de Noronha (−32,4°), Atol das Rocas, São Pedro e São Paulo
#: (−29,3°) e Trindade — um mapa de qualquer uma dessas unidades de conservação
#: recebia uma LAEA genérica em vez da projeção oficial do país.
BRAZIL_BOUNDS = (-74.01, -35.71, -25.28, 7.04)


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


def _resolve_layer_ids(spec: dict[str, Any], imports: dict[str, Any], label: str) -> list[Any]:
    """Resolve identificadores ou nomes de camada, recusando os que não existem.

    ``spec`` é o dicionário que carrega ``layer_ids``/``layers`` (o
    ``second_map`` do pedido, tipicamente). A extração usa ``as_id_list`` em
    vez de ``spec.get("layer_ids") or spec.get("layers") or []`` cru: esse
    padrão antigo não validava o tipo, e ``second_map: {"layer_ids": 99}``
    estourava ``TypeError: 'int' object is not iterable`` na iteração abaixo.
    """
    project = imports["QgsProject"].instance()
    raw_ids: list[str] | None = None
    for key in ("layer_ids", "layers"):
        candidate = as_id_list(spec, key, allow_single=True, label=f"{label}.{key}")
        if candidate:
            raw_ids = candidate
            break
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


def _resolve_output_path(params: dict[str, Any]) -> Path | None:
    """Caminho de saída absoluto e nativo do sistema, ou None quando não há.

    Dois acidentes que a versão anterior deixava passar, ambos vindos de
    usuário colando um caminho de outra máquina ou escrevendo só o nome:

    * um caminho do Windows ("C:\\Users\\...\\mapa.png") num QGIS em Linux/macOS
      é, para o POSIX, um nome de arquivo relativo com barras invertidas — a
      exportação criava um arquivo chamado literalmente ``C:\\Users\\...`` na
      pasta corrente e reportava sucesso;
    * um caminho relativo ("mapa.png", "saida/mapa.png") ia parar na pasta
      corrente do processo do QGIS, que o usuário não conhece.

    Os dois viram recusa com o caminho absoluto pedido de volta.
    """
    raw = params.get("output_path")
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    problem = classify_output_path(text)
    if problem == "foreign":
        raise CompositionError(
            f"output_path parece um caminho do Windows ({text!r}), mas este QGIS roda em "
            f"{platform.system() or 'outro sistema'}. Informe um caminho absoluto deste computador, "
            f"por exemplo {Path.home() / 'mapa.png'}."
        )
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    if problem == "relative":
        raise CompositionError(
            f"output_path precisa ser um caminho absoluto; recebido {text!r}, que seria gravado "
            f"na pasta corrente do QGIS, sem que o usuário saiba onde. Informe a pasta completa, "
            f"por exemplo {Path.home() / text}."
        )
    return Path(os.path.normpath(str(path)))


#: Trechos do nome oficial do CRS (registro EPSG, em inglês) que ganham
#: tradução na linha de crédito de mapas nas línguas latinas. "UTM zone 24S"
#: num mapa em português lia-se como mistura de línguas; o código EPSG, que é
#: o que se cita, continua ao lado.
_CRS_LABEL_TRANSLATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "pt-BR": (("UTM zone", "UTM zona"), ("Brazil Polyconic", "Policônica do Brasil"), ("Polyconic", "Policônica")),
    "es": (("UTM zone", "UTM zona"), ("Brazil Polyconic", "Policónica de Brasil"), ("Polyconic", "Policónica")),
    "it": (("UTM zone", "UTM zona"), ("Brazil Polyconic", "Policonica del Brasile"), ("Polyconic", "Policonica")),
    "fr": (("Brazil Polyconic", "Polyconique du Brésil"), ("Polyconic", "Polyconique")),
}


def _localised_crs_label(crs: Any, map_language: str = "pt-BR") -> str:
    description = str(crs.description() or crs.authid() or "")
    for source, target in _CRS_LABEL_TRANSLATIONS.get(map_language, ()):
        description = description.replace(source, target)
    authid = str(crs.authid() or "")
    return f"{description} ({authid})" if authid else description


def _format_scale(denominator: int, map_language: str = "pt-BR") -> str:
    """"1:250.000" em português, "1:250,000" em inglês, "1:250 000" em francês.

    O separador de milhar vem de maptext.py (símbolo de agrupamento do CLDR
    por língua). Sem o parâmetro cai em pt-BR, que é o que os laudos e as
    notas — escritos em português — continuam usando; a versão localizada só
    vai para o que o compositor escreve no papel.
    """
    return f"1:{int(denominator):,}".replace(",", maptext(map_language, "separador_milhar"))


#: Resolução do nível 0 do esquema Web Mercator, em metros por pixel no
#: equador. É a constante que liga escala impressa a nível de zoom de tiles.
WEB_MERCATOR_RESOLUTION_Z0 = 156543.03392


def _required_tile_zoom(scale_denominator: float, latitude_degrees: float) -> int:
    """Nível de zoom de tiles que a escala impressa exige nesta latitude."""
    import math as _math

    if scale_denominator <= 0:
        return 0
    # 0,00028 m é o tamanho de pixel de referência da OGC (~90,7 dpi), que é o
    # que as bibliotecas de tiles usam para converter escala em nível.
    resolucao_alvo = scale_denominator * 0.00028
    latitude = max(-85.0, min(85.0, latitude_degrees))
    resolucao_z0 = WEB_MERCATOR_RESOLUTION_Z0 * _math.cos(_math.radians(latitude))
    if resolucao_alvo <= 0 or resolucao_z0 <= 0:
        return 0
    return max(0, int(round(_math.log2(resolucao_z0 / resolucao_alvo))))


def _basemap_zoom_advice(layers: list[Any], fitted: Any, map_crs: Any, imports: dict[str, Any]) -> list[str]:
    """Avisa quando o mapa de base não tem tile na escala pedida.

    Uma camada XYZ com zmax 7 num mapa a 1:32.000 desenha um quadro em branco,
    aparece na legenda e passa na auditoria — o mesmo defeito de "está na
    legenda e não no mapa", só que por resolução em vez de por recorte.
    """
    import re as _re

    notes: list[str] = []
    try:
        centro_y = (fitted.ymin + fitted.ymax) / 2.0
        centro_x = (fitted.xmin + fitted.xmax) / 2.0
        geografico = imports["QgsCoordinateReferenceSystem"]("EPSG:4326")
        if map_crs.isValid() and geografico.isValid() and map_crs.authid() != "EPSG:4326":
            transform = imports["QgsCoordinateTransform"](map_crs, geografico, imports["QgsProject"].instance())
            ponto = transform.transform(imports["QgsPointXY"](centro_x, centro_y))
            latitude = ponto.y()
        else:
            latitude = centro_y
    except Exception:
        latitude = 0.0

    exigido = _required_tile_zoom(float(fitted.scale_denominator), latitude)
    for layer in layers:
        try:
            fonte = str(layer.source() or "")
        except Exception:
            continue
        if "type=xyz" not in fonte:
            continue
        achado = _re.search(r"zmax=(\d+)", fonte)
        if not achado:
            continue
        zmax = int(achado.group(1))
        if zmax < exigido:
            notes.append(
                f"O mapa de base {layer.name()!r} só tem tiles até o zoom {zmax}, e a escala "
                f"{_format_scale(int(fitted.scale_denominator))} exige o zoom {exigido}: nesta "
                "escala ele aparece na legenda e não desenha nada. Use uma fonte com mais níveis, "
                "ou componha numa escala mais aberta."
            )
    return notes


def _basemap_attributions(layers: list[Any]) -> list[str]:
    """Créditos de licença das camadas de base presentes no mapa.

    Um mapa de base é dado de terceiro sob licença, e quase toda licença de
    tiles exige o crédito na peça publicada. Depender de o usuário lembrar de
    repetir isso em data_source é como perder a procedência: o crédito existe
    na camada, então ele entra sozinho na linha de crédito.
    """
    creditos: list[str] = []
    for layer in layers:
        try:
            texto = str(layer.attribution() or "").strip()
        except Exception:
            continue
        if texto and texto not in creditos and "sem atribuição declarada" not in texto:
            creditos.append(texto)
    return creditos


#: Grafias aceitas para ``orientation: "auto"`` — a orientação é escolhida
#: pela proporção do recorte, não pelo padrão paisagem.
AUTO_ORIENTATION_TERMS = frozenset({"auto", "automatic", "automatica", "automática", "automatique", "automatisch"})


def _orientation_is_auto(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in AUTO_ORIENTATION_TERMS


def resolve_data_sources(
    value: Any, layers: list[tuple[str, ...]]
) -> tuple[str, dict[str, str], list[str]]:
    """Interpreta ``data_source`` como texto único ou como procedência por camada.

    ``layers`` é ``[(id, nome, fonte_dos_metadados[, derivada_de])]``; uma
    camada derivada de outra pelo SIGMAI (divisa, nomes — ``derivada_de`` é o
    id da origem) herda a fonte da origem, não conta como "sem fonte" e não
    aparece na linha de crédito. Aceita:

    * texto — uma fonte para o mapa inteiro (comportamento original);
    * dicionário ``{camada: fonte}`` — a chave é o id ou o nome da camada
      (sem diferenciar maiúsculas); uma chave que não bate com nenhuma
      camada é recusada com a lista, porque uma fonte atribuída à camada
      errada é procedência falsa;
    * lista ``[{"layer": ..., "source": ...}]`` — o mesmo, em forma de lista.

    Camadas sem fonte declarada herdam a dos metadados da própria camada
    (``rights``/atribuição), quando existir, com nota. Devolve o texto da
    linha de crédito ("IBGE 2024 (Municípios); CEUC/SEMA (Parque)"), o mapa
    ``{id: fonte}`` para a legenda e as notas.
    """
    notes: list[str] = []
    if value is None or (isinstance(value, str) and not value.strip()):
        return "", {}, notes
    if isinstance(value, (int, float)):
        return str(value), {}, notes
    if isinstance(value, str):
        return value.strip(), {}, notes

    entries: list[tuple[str, str]] = []
    if isinstance(value, dict):
        entries = [(str(k), str(v)) for k, v in value.items()]
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict) or "layer" not in item or "source" not in item:
                raise CompositionError(
                    "data_source em lista precisa de objetos {\"layer\": <id ou nome>, \"source\": <texto>}; "
                    f"recebido {item!r}."
                )
            entries.append((str(item["layer"]), str(item["source"])))
    else:
        raise CompositionError(
            f"data_source precisa ser texto, dicionário {{camada: fonte}} ou lista de {{layer, source}}; "
            f"recebido {type(value).__name__}."
        )

    layers = [tuple(entry) + ("",) * (4 - len(entry)) for entry in layers]
    derived_of = {layer_id: parent for layer_id, _, _, parent in layers if parent}
    by_key: dict[str, tuple[str, str]] = {}
    for layer_id, name, _, _ in layers:
        by_key[layer_id.lower()] = (layer_id, name)
        by_key[name.lower()] = (layer_id, name)
    per_layer: dict[str, str] = {}
    unknown: list[str] = []
    for key, source in entries:
        match = by_key.get(key.strip().lower())
        if match is None:
            unknown.append(key)
            continue
        per_layer[match[0]] = source.strip()
    if unknown:
        known = ", ".join(f"{name} ({layer_id})" for layer_id, name, _, _ in layers)
        raise CompositionError(
            "data_source cita camadas que não estão no mapa: " + ", ".join(repr(k) for k in unknown) +
            f". Camadas do mapa: {known}. Use o id ou o nome exato de cada camada."
        )
    for layer_id, name, metadata_source, _ in layers:
        if layer_id not in per_layer and metadata_source.strip() and layer_id not in derived_of:
            per_layer[layer_id] = metadata_source.strip()
            notes.append(f"A fonte de {name!r} veio dos metadados da própria camada: {metadata_source.strip()!r}.")
    for layer_id, parent in derived_of.items():
        if layer_id not in per_layer and parent in per_layer:
            per_layer[layer_id] = per_layer[parent]
    missing = [name for layer_id, name, _, _ in layers if layer_id not in per_layer and layer_id not in derived_of]
    if missing:
        notes.append(
            "Sem fonte declarada para: " + ", ".join(repr(n) for n in missing) +
            ". Acrescente-as em data_source para que a procedência cubra todas as camadas."
        )
    # Texto do crédito: fontes distintas, cada uma seguida das camadas que cobre
    # (as derivadas ficam de fora: a origem já responde por elas).
    grouped: dict[str, list[str]] = {}
    names = {layer_id: name for layer_id, name, _, _ in layers}
    for layer_id, source in per_layer.items():
        if layer_id in derived_of:
            continue
        grouped.setdefault(source, []).append(names.get(layer_id, layer_id))
    credit = "; ".join(f"{source} ({', '.join(covered)})" for source, covered in grouped.items())
    return credit, per_layer, notes


def _layer_metadata_source(layer: Any) -> str:
    """Atribuição declarada nos metadados/propriedades da camada, se houver."""
    try:
        rights = [str(r).strip() for r in (layer.metadata().rights() or []) if str(r).strip()]
        if rights:
            return "; ".join(rights)
    except Exception:
        pass
    try:
        attribution = str(layer.attribution() or "").strip()
        if attribution:
            return attribution
    except Exception:
        pass
    return ""


def _credit_line(params: dict[str, Any], crs_label: str, date_label: str, map_language: str = "pt-BR",
                 basemap_credits: list[str] | None = None, source_text: str | None = None) -> str:
    # as_text: data_source/map_author/organization nulos viravam o texto
    # "None" na linha de crédito (str(None) == "None"), porque None é
    # truthy... não, mas str(None).strip() == "None" é não-vazio e passava no
    # "if source:" abaixo mesmo sem o usuário ter pedido nada.
    pieces = []
    if source_text is not None:
        source = source_text.strip()
    else:
        source = as_text(params, "data_source", default="", label="data_source").strip()
    # O crédito do mapa de base entra junto com a fonte declarada: é fonte de
    # dado como qualquer outra, e a licença o exige na peça publicada.
    partes_fonte = [source] if source else []
    for credito in (basemap_credits or []):
        if credito not in partes_fonte:
            partes_fonte.append(credito)
    if partes_fonte:
        pieces.append(f"{maptext(map_language, 'fonte')}{'; '.join(partes_fonte)}")
    author = as_text(params, "map_author", default="", label="map_author").strip()
    if author:
        pieces.append(f"{maptext(map_language, 'elaboracao')}{author}")
    organization = as_text(params, "organization", default="", label="organization").strip()
    if organization:
        pieces.append(organization)
    if crs_label:
        pieces.append(crs_label)
    if date_label:
        pieces.append(date_label)
    pieces.append(maptext(map_language, "credito_ferramenta"))
    # Defeito 3 (RTL) — NÃO inverter a ordem das peças aqui, de propósito.
    #
    # A primeira tentativa desta correção invertia `pieces` para línguas RTL,
    # partindo do pressuposto de que QgsLayoutItemLabel desenha a string
    # sempre da esquerda para a direita em ordem lógica, ignorando a direção
    # do script. Comparar lado a lado a mesma linha de crédito COM e SEM essa
    # inversão (mesmos dados, só a ordem das peças mudando) mostrou o
    # contrário: o renderizador de texto do QGIS já aplica o algoritmo Unicode
    # de bidirecionalidade por linha, e o pressuposto era falso — a versão SEM
    # inversão é a que coloca "Fonte:" (a peça logicamente primeira) no lado
    # direito da linha (o que um leitor de árabe/hebraico encontra primeiro),
    # exatamente o resultado que a inversão tentava produzir à força; invertida,
    # "Fonte:" ia parar à ESQUERDA — o oposto do pedido. A condição para essa
    # bidirecionalidade funcionar é a linha começar com um caractere de
    # direção forte RTL, o que passa a valer aqui assim que "Fonte:"/
    # "Elaboração:" saem traduzidos (defeito 1) em vez de ficarem em português
    # na frente do valor em árabe/hebraico — as duas correções trabalham
    # juntas. Ficou como está por não termos como validar exaustivamente o
    # comportamento de bidi do Qt/QGIS para toda combinação de peças (uma
    # organization em alfabeto latino como primeira peça preenchida, por
    # exemplo, ainda pode nascer sem nenhum caractere RTL forte e sair não
    # invertida) — inventar uma heurística extra por cima do bidi nativo é
    # exatamente o tipo de solução frágil que o regulamento deste defeito pede
    # para não fazer; ver o relatório da correção para o limite documentado.
    return " · ".join(pieces)


# ---------------------------------------------------------------------------
# Compositor
# ---------------------------------------------------------------------------

def compose_map(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Compõe, exporta e audita um mapa completo.

    Ponto único de conversão: qualquer ``ParameterError`` levantada por
    ``params.py`` ao longo de toda a composição — em ``compose_map`` e nas
    funções internas que ele chama, como ``_apply_labels`` ou
    ``_add_inset_map`` — vira ``CompositionError`` aqui. Do lado de quem
    chamou a ferramenta as duas são idênticas (uma recusa com mensagem
    acionável); a distinção só evita que ``params.py`` precise conhecer
    ``CompositionError``.
    """
    try:
        return _compose_map(params, context)
    except ParameterError as exc:
        raise CompositionError(str(exc)) from exc


def _compose_map(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown_parameters(params)
    imports = _imports()
    project = imports["QgsProject"].instance()

    layers = _resolve_layers(params, imports)
    second_map_spec = params.get("second_map") or None
    if second_map_spec is not None and not isinstance(second_map_spec, dict):
        raise CompositionError("second_map precisa ser um objeto com layer_ids e, opcionalmente, panel_title.")
    # panels: lista de painéis ADICIONAIS ao principal, cada um como
    # second_map ({layer_ids, subject_layer_id?, panel_title?, margin_percent?}).
    # second_map continua valendo como atalho para um único painel extra.
    panels_raw = params.get("panels")
    if panels_raw is not None and second_map_spec is not None:
        raise CompositionError("Use second_map (um painel extra) OU panels (lista de painéis extras), não os dois.")
    if panels_raw is not None:
        if not isinstance(panels_raw, list) or not panels_raw or not all(isinstance(p, dict) for p in panels_raw):
            raise CompositionError("panels precisa ser uma lista de objetos {layer_ids, subject_layer_id?, panel_title?}.")
        if len(panels_raw) > 7:
            raise CompositionError(f"panels aceita até 7 painéis extras (8 quadros); recebidos {len(panels_raw)}.")
    extra_specs: list[dict[str, Any]] = [second_map_spec] if second_map_spec is not None else list(panels_raw or [])
    # Daqui em diante second_map_spec só diz se HÁ painéis extras.
    second_map_spec = extra_specs[0] if extra_specs else None

    # As camadas dos painéis extras entram na mesma passada de estilo: estilizar
    # só as do primeiro deixava o painel b) com a cor aleatória que o QGIS
    # sorteou, ao lado de um painel a) com a paleta segura.
    styling_targets = list(layers)
    for index, spec in enumerate(extra_specs):
        for layer in _resolve_layer_ids(spec, imports, _panel_label(index)):
            if all(layer.id() != existing.id() for existing in styling_targets):
                styling_targets.append(layer)

    # apply_style é um enum fechado ('missing'/'all'/'none'); um valor fora
    # disso caía no ramo que força restilo em TODAS as camadas em silêncio —
    # symbology.apply_default_symbology recusa isso explicitamente.
    apply_style_value = as_text(params, "apply_style", default="missing", label="apply_style").strip().lower()
    # Aqui só a PRÉVIA (dry_run=True): valida apply_style e diz o que seria
    # reestilizado, sem tocar em nenhuma camada. A aplicação de verdade fica
    # para depois da última validação de parâmetro — uma página inexistente
    # ou um dpi absurdo recusados mais abaixo não podem deixar para trás o
    # projeto do usuário com a simbologia trocada por um mapa que não saiu.
    composing_dry_run = bool(context.get("dry_run"))
    styling = apply_default_symbology(styling_targets, apply_style_value, dry_run=True)
    styling_verb = "seria reestilizada" if composing_dry_run else "foi reestilizada"
    styling_notes = [
        f"A camada {entry['layer']!r} {styling_verb}: {entry['note']}."
        for entry in styling if entry.get("note")
    ]
    # ``strict=True``: se o assistente pediu um formato que não existe, é melhor
    # dizer isso do que devolver, em silêncio, uma folha A4 que ninguém pediu.
    orientation_auto = _orientation_is_auto(params.get("orientation"))
    try:
        page: PageSpec = resolve_page(
            params.get("page"), None if orientation_auto else params.get("orientation"), params.get("margin_mm"),
            strict=params.get("page") is not None,
        )
    except ValueError as exc:
        raise CompositionError(str(exc)) from exc

    template = _resolve_template(params)

    # title/subtitle cedo: título nulo imprimia o texto "None" no mapa, e
    # subtitle nulo fazia bool(str(None).strip()) avaliar True — ligando o
    # subtítulo mesmo sem nenhum texto ter sido pedido.
    title_value = as_text(params, "title", default="", label="title").strip()
    subtitle_value = as_text(params, "subtitle", default="", label="subtitle").strip()

    # data_source por camada ("IBGE 2024" para a malha, "CEUC/SEMA" para a
    # UC) entra na legenda e na linha de crédito; um texto único continua
    # valendo para o mapa inteiro. Resolvido cedo: uma camada citada que não
    # está no mapa é recusa de parâmetro, antes de qualquer mutação.
    source_text, layer_sources, source_notes = resolve_data_sources(
        params.get("data_source"),
        [(layer.id(), layer.name(), _layer_metadata_source(layer),
          str(_quiet(lambda: layer.customProperty("sigmai/derived_from", "")) or "")) for layer in styling_targets],
    )
    if not isinstance(params.get("data_source"), (dict, list)):
        source_notes = []  # texto único: as notas de cobertura por camada não se aplicam

    # map_language escolhe a língua dos textos que o PRÓPRIO compositor
    # escreve — "Fonte:"/"Elaboração:", o título padrão quando ninguém pede
    # um, "Legenda", "Painel A/B", o crédito da ferramenta (ver maptext.py).
    # A grafia é tolerante ("EN", "en_US", "jp", "zh-TW" resolvem; ver
    # resolve_language), mas um código que não bate com nenhuma língua coberta
    # é recusado com a lista — o mesmo tratamento de page/template. Cair em
    # português com uma nota, como se fazia, entregava ao usuário um mapa
    # em língua que ele não pediu e que só o assistente ficava sabendo.
    map_language_raw = as_text(params, "map_language", default="pt-BR", label="map_language").strip() or "pt-BR"
    map_language, map_language_known = resolve_language(map_language_raw)
    if not map_language_known:
        raise CompositionError(
            f"map_language={map_language_raw!r} não corresponde a nenhuma língua coberta pelos textos do "
            "mapa. Línguas reconhecidas: " + ", ".join(sorted(MAP_TEXT)) + " (códigos regionais como "
            "en-US, zh-TW ou pt-PT também resolvem). Escolha uma delas; os textos do usuário (título, "
            "fonte, autor) podem estar em qualquer língua."
        )
    map_language_rtl = map_language in RTL_LANGUAGES

    # As bandeiras nunca usam bool() do Python: bool("false") vale True, e foi
    # assim que confirm_overwrite:"false" (string) sobrescreveu arquivo do
    # usuário em silêncio. Cada conversão registra uma nota, mesclada em
    # `notes` mais abaixo (a lista ainda não existe neste ponto do fluxo).
    flag_notes: list[str] = []

    def _flag(key: str, default: bool) -> bool:
        value, note = as_flag(params, key, default)
        if note:
            flag_notes.append(note)
        return value

    include_legend = _flag("include_legend", True)
    include_scale_bar = _flag("include_scale_bar", True)
    include_scale_text = _flag("include_scale_text", True)
    include_north = _flag("include_north_arrow", True)
    include_grid = _flag("include_grid", True)
    include_subtitle = bool(subtitle_value)
    include_logo = _flag("include_logo", False)
    include_inset = _flag("include_inset", False)

    # grid_style é validado uma vez aqui e reaproveitado nos dois lugares que
    # desenham grade (mapa principal e painel de comparação).
    grid_style_value = _resolve_grid_style(params)

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
        panels=1 + len(extra_specs),
    )
    # solve_layout (layoutgrid.py) recusa página/margens combinadas que não
    # sobram espaço com um ValueError — mesmo tratamento que resolve_page
    # recebe acima: a exceção de programador vira CompositionError na
    # fronteira de compose_map, nunca escapa crua para quem chamou a ferramenta.
    try:
        plan = solve_layout(**layout_request)
    except ValueError as exc:
        raise CompositionError(str(exc)) from exc
    frame = plan.map_frame()

    # --- sistema de referência ------------------------------------------
    notes: list[str] = list(plan.notes) + styling_notes + flag_notes + source_notes
    requested_crs = _resolve_map_crs_text(params)
    if requested_crs:
        map_crs = imports["QgsCoordinateReferenceSystem"](requested_crs)
        if not map_crs.isValid():
            raise CompositionError(
                f"map_crs inválido: {requested_crs!r}. Use um código de sistema de referência, "
                "por exemplo 'EPSG:4674' (SIRGAS 2000) ou 'EPSG:31983' (SIRGAS 2000 / UTM 23S)."
            )
    else:
        map_crs = project.crs()
    map_crs_label = ""

    # Projeto sem CRS definido acontece com frequência em projetos novos e em
    # scripts. Um CRS inválido não é geográfico nem projetado: a reprojeção
    # automática não disparava, os graus eram tomados por metros e a escala saía
    # 1:0, estourando lá na frente com um erro que não dizia nada.
    if not map_crs.isValid():
        herdado = next(
            (layer.crs() for layer in layers if layer.crs().isValid()), None
        )
        if herdado is None:
            raise CompositionError(
                "O projeto não tem sistema de coordenadas definido e nenhuma das camadas "
                "informadas declara o seu. Defina o CRS do projeto no QGIS, ou passe map_crs "
                "com o código do sistema (por exemplo 'EPSG:31983')."
            )
        map_crs = herdado
        notes.append(
            f"O projeto está sem sistema de coordenadas definido; foi adotado o da primeira "
            f"camada válida ({_crs_identifier(map_crs)}). Defina o CRS do projeto no QGIS "
            "para que este mapa e os próximos usem sempre o mesmo."
        )

    # Assunto e contexto são coisas diferentes. "Mapa do parque, mostrando os
    # municípios em volta" enquadra o parque e desenha os municípios; usar a
    # união de todas as camadas enquadraria o estado inteiro e o parque
    # sumiria. Sem isto, a única forma de obter um recorte de detalhe era
    # remover as camadas de contexto — e perder o contexto.
    # subject_layer_id aceita um id/nome ou uma LISTA: num mapa de campanha o
    # assunto são os pontos E a trilha, e o recorte tem de conter os dois.
    subject_raw = params.get("subject_layer_id")
    if isinstance(subject_raw, list):
        subject_ids = [str(v).strip() for v in subject_raw if str(v).strip()]
    else:
        subject_ids = [as_text(params, "subject_layer_id", default="", label="subject_layer_id").strip()]
        subject_ids = [v for v in subject_ids if v]
    extent_layers = layers
    if subject_ids:
        subject = [layer for layer in layers if layer.id() in subject_ids or layer.name() in subject_ids]
        unknown = [v for v in subject_ids if all(layer.id() != v and layer.name() != v for layer in layers)]
        if not subject or unknown:
            raise CompositionError(
                f"subject_layer_id não corresponde a nenhuma camada do mapa: {', '.join(unknown or subject_ids)}. "
                "Camadas informadas: " + ", ".join(f"{layer.name()} ({layer.id()})" for layer in layers) + "."
            )
        extent_layers = subject
        names = ", ".join(repr(layer.name()) for layer in subject)
        notes.append(
            f"Recorte definido pela{'s camadas' if len(subject) > 1 else ' camada'} de assunto {names}; "
            "as demais entram como contexto."
        )

    extent = _combined_extent(extent_layers, map_crs, imports)

    # Figura para periódico: a página É a figura, na largura final impressa.
    # A altura é escolhida para que o quadro do mapa tenha a proporção do
    # recorte (sem encher a folha de faixa vazia), até figure_max_height_mm.
    figure_width = _resolve_figure_width(params)
    print_width_mm: float | None = None
    if figure_width is not None:
        figure_height = as_number(params, "figure_height_mm", None, minimum=20.0, maximum=600.0, label="figure_height_mm")
        max_height = as_number(params, "figure_max_height_mm", default=FIGURE_DEFAULT_MAX_HEIGHT_MM, minimum=20.0, maximum=600.0,
                               label="figure_max_height_mm")
        if not params.get("template") and not params.get("layout_template"):
            template = "publicacao"
            layout_request["template"] = template
        margin_for_figure = params.get("margin_mm", FIGURE_MARGIN_MM)
        page, plan = _solve_figure_page(
            figure_width, figure_height, max_height, margin_for_figure, extent, layout_request,
        )
        layout_request["page"] = page  # as passadas seguintes (barra sob o mapa) resolvem nesta página
        frame = plan.map_frame()
        orientation_auto = False
        print_width_mm = float(figure_width)
        notes.append(
            f"Figura para periódico: página de {page.width_mm:g} x {page.height_mm:g} mm (largura final impressa"
            + (f", coluna {params.get('journal_column')}" if params.get("journal_column") else "")
            + f"), template {template!r}, fontes de pelo menos {MIN_FONT_PT:g} pt nessa largura."
        )

    auto_projected_crs, auto_projected_note = as_flag(params, "auto_projected_crs", True)
    if auto_projected_note:
        notes.append(auto_projected_note)
    if map_crs.isGeographic() and auto_projected_crs:
        # A projeção é escolhida pelo recorte que vai ao papel, não pelo recorte
        # cru dos dados: o quadro alarga a extensão para casar com sua proporção,
        # e um segundo painel pode cobrir uma área muito maior que o primeiro.
        decision_extent = _aspect_expanded(extent, frame.width, frame.height, imports)
        for index, spec in enumerate(extra_specs):
            slot_key = f"map_{index + 2}"
            if slot_key not in plan.slots:
                continue
            panel_layers = _resolve_layer_ids(spec, imports, _panel_label(index))
            if panel_layers:
                panel_extent = _combined_extent(
                    _subject_subset(panel_layers, spec.get("subject_layer_id", "")),
                    map_crs, imports,
                )
                frame_n = plan.slots[slot_key]
                decision_extent.combineExtentWith(
                    _aspect_expanded(panel_extent, frame_n.width, frame_n.height, imports)
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

    # margin_percent: "cinco" ou null estouravam ValueError cru dentro de
    # fit_extent_to_frame; negativo era só grampeado a 0 em silêncio por
    # max(0.0, ...) lá dentro — minimum=0.0 aqui recusa antes disso.
    margin_percent_value = as_number(params, "margin_percent", default=5.0, minimum=0.0, maximum=100.0, label="margin_percent")

    # dpi só era lido na hora de exportar. Sem output_path, um valor absurdo
    # passava calado — e um parâmetro aceito sem efeito é o mesmo defeito de
    # improvisar em silêncio que o resto do arquivo combate.
    as_number(params, "dpi", default=300, minimum=50, maximum=1200, integer=True, label="dpi")
    round_scale_value, round_scale_note = as_flag(params, "round_scale", True)
    if round_scale_note:
        notes.append(round_scale_note)

    def _fit(target_frame: Rect) -> Any:
        return fit_extent_to_frame(
            extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum(),
            target_frame.width, target_frame.height,
            margin_percent=margin_percent_value,
            snap_to_round_scale=round_scale_value,
            map_units_per_metre=_map_units_per_metre(map_crs, extent, imports),
        )

    # orientation="auto": a folha gira se, resolvido o layout na outra
    # orientação, o quadro aproveita o recorte numa escala pelo menos 12%
    # maior. É a mesma conta de _orientation_advice, só que aplicada em vez
    # de aconselhada — o mapa do Parque das Carnaúbas saiu em paisagem com a
    # metade leste vazia enquanto a nota dizia que em retrato caberia melhor.
    if orientation_auto:
        flipped = _better_orientation(extent, frame, page, template, layout_request, annotation_gutter)
        if flipped is not None:
            try:
                page = resolve_page(page.name if page.name.upper() in PAGE_SIZES else
                                    {"width_mm": page.height_mm, "height_mm": page.width_mm, "name": page.name},
                                    flipped, params.get("margin_mm"))
                layout_request["page"] = page
                plan = solve_layout(**layout_request)
            except ValueError as exc:
                raise CompositionError(str(exc)) from exc
            frame = plan.map_frame()
            notes.append(
                f"Orientação escolhida automaticamente: {'retrato' if flipped == 'portrait' else 'paisagem'} — "
                "o recorte aproveita melhor a folha nessa orientação."
            )
        else:
            notes.append(f"Orientação escolhida automaticamente: {'paisagem' if page.orientation == 'landscape' else 'retrato'}.")

    # Arranjo dos itens de apoio (coluna lateral × faixa inferior) escolhido
    # pela forma dos DADOS, não só pela da página: um estado alto e estreito
    # numa A4 retrato saía num quadro quase quadrado (faixa inferior), com as
    # laterais vazias e a escala 1:6.300.000; com coluna lateral o quadro é
    # alto e a escala sobe. Mesmo critério de _better_orientation: só troca
    # quando o ganho passa de 12 %.
    if not extra_specs and not params.get("arrangement"):
        better = _better_arrangement(extent, frame, plan, layout_request)
        if better is not None:
            layout_request["arrangement"] = better
            try:
                plan = solve_layout(**layout_request)
            except ValueError as exc:
                raise CompositionError(str(exc)) from exc
            frame = plan.map_frame()
            notes.append(
                "Itens de apoio em "
                + ("coluna lateral" if better == "coluna_lateral" else "faixa inferior")
                + ": com esse arranjo o quadro aproveita melhor a forma do recorte."
            )
    elif params.get("arrangement"):
        chosen = str(params.get("arrangement")).strip().lower()
        if chosen not in ("coluna_lateral", "faixa_inferior", "auto"):
            raise CompositionError(
                f"arrangement desconhecido: {params.get('arrangement')!r}. Valores aceitos: 'auto', 'coluna_lateral', 'faixa_inferior'."
            )
        layout_request["arrangement"] = chosen
        try:
            plan = solve_layout(**layout_request)
        except ValueError as exc:
            raise CompositionError(str(exc)) from exc
        frame = plan.map_frame()

    fitted = _fit(frame)

    # Segunda passada só quando a primeira revela que a barra não cabe legível
    # na coluna lateral. A escala só é conhecida depois do ajuste, então não há
    # como decidir isso antes de resolver o layout uma vez.
    if _scalebar_needs_full_width(plan, fitted, frame, include_scale_bar, second_map_spec):
        previous_notes = set(plan.notes)
        try:
            plan = solve_layout(**layout_request, scale_bar_under_map=True)
        except ValueError as exc:
            raise CompositionError(str(exc)) from exc
        frame = plan.map_frame()
        fitted = _fit(frame)
        notes.extend(note for note in plan.notes if note not in previous_notes)

    # As notas do ajuste automático só entram se o ajuste automático valer: com
    # escala fixada elas descrevem uma decisão que foi substituída, e uma nota
    # que contradiz o resultado é pior do que nota nenhuma.
    fit_notes = list(fitted.notes)

    # Escala pedida explicitamente. "Faça em 1:25.000" é o pedido cartográfico
    # mais comum que existe — numa dissertação a escala costuma ser imposta pela
    # norma, não escolhida. O ajuste automático continua valendo como padrão; o
    # que este ramo faz é obedecer quando alguém decidiu.
    requested_scale = as_number(params, "scale", None, minimum=1.0, integer=True, label="scale")
    if requested_scale:
        minimum_scale = fitted.raw_scale_denominator / (1.0 + 2.0 * max(0.0, margin_percent_value) / 100.0)
        if requested_scale < minimum_scale * 0.999:
            # Os denominadores passam por _format_scale: um .replace(",", ".")
            # na frase inteira trocava também as vírgulas do texto por pontos
            # ("ocupam. cortando parte deles.") — recusa certa, redigida errada.
            raise CompositionError(
                f"A escala pedida ({_format_scale(int(requested_scale))}) não cabe: nessa escala o quadro "
                f"mostraria menos terreno do que os dados ocupam, cortando parte deles. "
                f"A maior escala que ainda contém tudo é aproximadamente "
                f"{_format_scale(int(math.ceil(minimum_scale)))}. Peça essa ou uma mais aberta, ou omita "
                f"'scale' para o SIGMAI escolher."
            )
        if int(requested_scale) != int(fitted.scale_denominator):
            fitted = _rescale(fitted, int(requested_scale))
            fit_notes = [
                note for note in fit_notes
                if "escala" not in note.lower() and "margem efetiva" not in note.lower()
            ]
            notes.append(
                f"Escala fixada em {_format_scale(int(requested_scale))} a pedido; "
                "o recorte foi centralizado e aberto até essa escala."
            )

    notes.extend(fit_notes)

    notes.extend(_empty_in_frame_advice(layers, extent_layers, fitted, map_crs, imports))
    notes.extend(_basemap_zoom_advice(layers, fitted, map_crs, imports))

    if not include_inset:
        notes.extend(_locator_advice(extent, layers, extent_layers, map_crs, imports))

    if not orientation_auto:
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
    panel_plans: list[dict[str, Any]] = []
    for index, spec in enumerate(extra_specs):
        slot_key = f"map_{index + 2}"
        if slot_key in plan.slots:
            panel_plans.append(_plan_comparison(spec, params, plan, map_crs, imports, slot=slot_key, label=_panel_label(index)))
    comparison_plan = panel_plans[0] if panel_plans else None  # compat: primeiro painel extra
    if panel_plans:
        comparison_same_scale, comparison_same_scale_note = as_flag(params, "comparison_same_scale", True)
        if comparison_same_scale_note:
            notes.append(comparison_same_scale_note)
        if comparison_same_scale:
            all_scales = [fitted.scale_denominator] + [pp["fitted"].scale_denominator for pp in panel_plans]
            shared = max(all_scales)
            if any(scale != shared for scale in all_scales):
                notes.append(
                    f"Os {len(all_scales)} painéis foram igualados em {_format_scale(shared, map_language)} — a escala "
                    "mais aberta de todos — para que a comparação visual entre eles seja honesta."
                )
            antes = (fitted.scale_denominator, panel_plans[0]["fitted"].scale_denominator)
            fitted = _rescale(fitted, shared)
            for pp in panel_plans:
                pp["fitted"] = _rescale(pp["fitted"], shared)
            notes.extend(_equalisation_cost_advice(antes, shared))
        else:
            # Escalas diferentes exigem que cada painel anuncie a sua. Uma barra
            # de escala única sob painéis desiguais afirma algo falso sobre
            # um deles.
            for pp in panel_plans:
                pp["per_panel_scale"] = True
            listed = ", ".join(
                _format_scale(scale, map_language)
                for scale in [fitted.scale_denominator] + [pp["fitted"].scale_denominator for pp in panel_plans]
            )
            notes.append(
                f"Painéis em escalas diferentes ({listed}); cada painel anuncia a sua escala "
                "e a barra única foi substituída por essa indicação."
            )

    explicit_layout_name = as_text(params, "layout_name", default="", label="layout_name").strip()
    layout_name = explicit_layout_name or _unique_layout_name(project, title_value or "Mapa SIGMAI")
    # Um layout_name que já existe no projeto é SUBSTITUÍDO — é o que quem
    # itera sobre o mesmo mapa quer. Sem nome explícito, cada composição cria
    # "Título (2)", "Título (3)"…, e o projeto acumula layouts órfãos que o
    # usuário não pediu; a nota abaixo avisa disso.
    replace_layout = explicit_layout_name and project.layoutManager().layoutByName(explicit_layout_name) is not None
    output_path = _resolve_output_path(params)

    # format e a extensão de output_path podem discordar (output_path
    # "mapa.png" com format "pdf"): antes disso gerava um PDF chamado .png sem
    # avisar. explicit_format sempre vence quando não há conflito; quando os
    # dois discordam, a composição é recusada em vez de escolher por conta.
    explicit_format = as_text(params, "format", default="", label="format").strip().lower()
    # Um format que não existe é recusado mesmo sem output_path: sem isto,
    # format='imagen' numa chamada só de layout era aceito calado — e o
    # assistente repetia o valor na exportação seguinte, aí sim para quebrar.
    if explicit_format and explicit_format not in SUPPORTED_FORMATS:
        raise CompositionError(
            f"Formato de saída inválido: {explicit_format!r}. "
            f"Use um destes: {', '.join(sorted(SUPPORTED_FORMATS))}."
        )
    suffix_format = output_path.suffix.lstrip(".").lower() if output_path is not None else ""
    if output_path is not None and explicit_format and suffix_format and explicit_format != suffix_format:
        raise CompositionError(
            f"output_path termina em '.{suffix_format}' mas format pede '{explicit_format}'. "
            f"Escolha um dos dois: troque a extensão do arquivo para '.{explicit_format}', "
            f"passe format='{suffix_format}', ou omita format para que a extensão decida."
        )
    if explicit_format:
        export_format = explicit_format
    elif output_path is not None:
        export_format = suffix_format
    else:
        export_format = "pdf"

    if context.get("dry_run"):
        return {
            "dry_run": True,
            "layout_name": layout_name,
            "plan": plan.to_dict(),
            "map_crs": _crs_identifier(map_crs, map_crs_label),
            "extent": fitted.to_dict(),
            "scale": _format_scale(fitted.scale_denominator),
            "layers": [{"id": layer.id(), "name": layer.name()} for layer in layers],
            # O que a composição faria à simbologia, sem tê-la feito: quais
            # camadas seriam reestilizadas e com que cor. Nenhum layer.setRenderer
            # foi chamado para gerar esta lista — ver apply_default_symbology.
            "styling_preview": styling,
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
        # O defeito mais grave do lote: bool("false") vale True em Python, e
        # confirm_overwrite:"false" (string) sobrescrevia o arquivo do usuário
        # em silêncio. as_flag nunca usa a conversão bool() do Python — só uma
        # lista fechada de grafias inequívocas — por isso não repete o acidente.
        confirm_overwrite, confirm_overwrite_note = as_flag(params, "confirm_overwrite", False)
        if confirm_overwrite_note:
            notes.append(confirm_overwrite_note)
        if output_path.exists() and not confirm_overwrite:
            raise CompositionError(
                f"O arquivo já existe: {output_path}. Passe confirm_overwrite=true para substituí-lo."
            )

    # --- simbologia -------------------------------------------------------
    # Primeira e única mutação do projeto: todos os parâmetros já foram
    # aceitos, o que sai daqui para a frente é um mapa ou uma falha de QGIS.
    styling = apply_default_symbology(styling_targets, apply_style_value, dry_run=False)

    # --- layout -----------------------------------------------------------
    if replace_layout:
        try:
            project.layoutManager().removeLayout(project.layoutManager().layoutByName(layout_name))
            notes.append(f"O layout {layout_name!r} já existia no projeto e foi substituído.")
        except Exception as exc:
            raise CompositionError(f"Não foi possível substituir o layout {layout_name!r}: {exc}") from exc
    elif not explicit_layout_name and layout_name != (title_value or "Mapa SIGMAI"):
        notes.append(
            f"Layout criado como {layout_name!r} porque já havia um com o nome do título; passe "
            "layout_name para substituir o anterior em vez de acumular layouts no projeto."
        )
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
        _apply_grid(map_item, fitted, map_crs, plan, imports, notes, grid_style_value)
        created["grid"] = "grid"

    # Rótulos das feições, quando pedidos
    label_field = as_text(params, "label_field", default="", label="label_field").strip()
    if label_field:
        labelled = _apply_labels(layers, params, label_field, plan, imports, notes)
        if labelled:
            created["labels"] = labelled

    # Inserto de localização
    if include_inset and "inset" in plan.slots:
        _add_inset_map(layout, map_item, layers, plan, params, fitted, map_crs, imports, mm, notes)
        created["inset_map"] = "map"

    # Título e subtítulo
    #
    # Quando ninguém pede título, "Mapa" (traduzido para map_language) é
    # usado em vez de deixar o item sem texto: CART001 do regulamento
    # ("Título presente") é ERROR — um mapa sem título reprova a auditoria de
    # propósito, porque título ausente não informa tema, recorte nem
    # propósito a quem lê. Traduzir o padrão mantém a regra satisfeita e o
    # mapa monolíngue; omitir o item trocaria "sem título" por "reprovado".
    title_text = title_value or maptext(map_language, "titulo_padrao")
    _add_label(
        layout, "title", title_text, plan.slots["title"], plan.fonts["title"], imports, mm,
        bold=True, align="center", notes=notes, fit=True,
    )
    created["title"] = "label"
    if include_subtitle and "subtitle" in plan.slots:
        _add_label(
            layout, "subtitle", subtitle_value, plan.slots["subtitle"], plan.fonts["subtitle"], imports, mm,
            align="center", notes=notes, fit=True,
        )
        created["subtitle"] = "label"

    # Legenda com TODAS as camadas desenhadas — dos dois painéis, quando há
    # comparação. Uma feição no segundo quadro sem entrada na legenda deixa o
    # leitor sem saber o que está vendo.
    if include_legend and "legend" in plan.slots:
        legend_layers = list(layers)
        for pp in panel_plans:
            for layer in pp.get("layers", []):
                if all(layer.id() != existing.id() for existing in legend_layers):
                    legend_layers.append(layer)
        _add_legend(layout, map_item, legend_layers, plan, params, imports, mm, map_language,
                    layer_sources=layer_sources, notes=notes)
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
        _add_scalebar(layout, map_item, bar_spec, plan, imports, mm, page, map_language)
        created["scale_bar"] = "scalebar"

    # Escala numérica
    if include_scale_text and "scale_text" in plan.slots:
        scale_caption = (
            maptext(map_language, "escalas_por_painel")
            if (comparison_plan or {}).get("per_panel_scale")
            else f"{maptext(map_language, 'escala_prefixo')}{_format_scale(fitted.scale_denominator, map_language)}"
        )
        _add_label(
            layout, "scale_text", scale_caption,
            plan.slots["scale_text"], plan.fonts["scale_text"], imports, mm, align="center",
        )
        created["scale_text"] = "label"

    # Rosa dos ventos como símbolo
    if include_north and "north" in plan.slots:
        kind = _add_north_arrow(layout, map_item, plan.slots["north"], imports, mm, notes, map_language)
        created["north_arrow"] = kind

    # Rodapé: fonte, autoria, CRS e data
    #
    # Defeito 3 (RTL): num mapa inteiramente em árabe/hebraico, ancorar o
    # rodapé sempre na margem ESQUERDA é a metade do defeito que dá para
    # corrigir sem depender de um controle de direção de texto que esta
    # versão do QGIS não expõe (a outra metade — a ordem interna dos
    # pedaços — é resolvida dentro de _credit_line). Alinhar à direita aqui
    # é o mínimo defensável citado no relatório da correção.
    crs_label = _localised_crs_label(map_crs, map_language)
    date_label = (
        as_text(params, "production_date", default="", label="production_date").strip()
        or _datetime.date.today().strftime("%d/%m/%Y")
    )
    _add_label(
        layout, "source", _credit_line(params, crs_label, date_label, map_language,
                                       _basemap_attributions(layers), source_text=source_text),
        plan.slots["footer"], plan.fonts["footer"], imports, mm,
        align=("right" if map_language_rtl else "left"),
    )
    created["source"] = "label"

    if include_logo and "logo" in plan.slots:
        logo_path = as_text(params, "logo_path", default="", label="logo_path").strip()
        if logo_path and Path(logo_path).exists():
            picture = imports["QgsLayoutItemPicture"](layout)
            picture.setId("logo")
            picture.setPicturePath(logo_path)
            layout.addLayoutItem(picture)
            _place(picture, plan.slots["logo"], imports, mm)
            created["logo"] = "picture"

    # Quadros extras (comparação a dois, ou figura com N painéis)
    for index, pp in enumerate(panel_plans):
        pp["main_scale"] = fitted.scale_denominator
        item_id = _build_comparison_map(
            layout, pp, params, plan, map_crs, imports, mm, notes, grid_style_value, map_language,
            index=index, total=1 + len(panel_plans),
        ).id()
        created[item_id] = "map"
    if panel_plans:
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
        print_width_mm=print_width_mm,
    )

    _reject_if_audit_found_blank_output(audit)

    result = {
        "layout_name": layout_name,
        "template": plan.template,
        "arrangement": plan.arrangement,
        "page": page.to_dict(),
        "print_width_mm": print_width_mm,
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

    # --- receita reproduzível -------------------------------------------
    # Gravada no layout (sobrevive no .qgz), nos metadados do PNG e, se
    # pedido, num JSON ao lado. É o que permite refazer o mapa quando o dado
    # muda (recompose_from_recipe) e escrever o parágrafo de Métodos.
    recipe_layers = list(layers)
    for pp in panel_plans:
        for extra in pp.get("layers", []):
            if all(extra.id() != existing.id() for existing in recipe_layers):
                recipe_layers.append(extra)
    recipe = _store_recipe(layout, params, recipe_layers, layer_sources, result, output_path, export_format, imports, notes)
    result["recipe"] = {"stored_in_layout": True, "embedded_in_output": recipe.get("embedded_in_output", False),
                        "recipe_path": recipe.get("recipe_path", ""), "created_at": recipe.get("created_at")}
    return result


def _store_recipe(
    layout: Any, params: dict[str, Any], layers: list[Any], layer_sources: dict[str, str], result: dict[str, Any],
    output_path: Path | None, export_format: str, imports: dict[str, Any], notes: list[str],
) -> dict[str, Any]:
    from ..qgis_actions.project_overview import redact_layer_source
    from .recipe import (
        RECIPE_PNG_KEY, RECIPE_PROPERTY, build_recipe, file_fingerprint, local_file_of_source, recipe_to_json,
    )

    described: list[dict[str, Any]] = []
    for layer in layers:
        source = redact_layer_source(layer)
        entry: dict[str, Any] = {
            "id": layer.id(), "name": layer.name(), "provider": str(_quiet(layer.providerType) or ""),
            "source": source, "crs": _crs_identifier(layer.crs()) if _quiet(layer.crs) is not None else "",
            "feature_count": _quiet(lambda: layer.featureCount()), "source_text": layer_sources.get(layer.id(), ""),
        }
        local = local_file_of_source(str(_quiet(layer.source) or ""))
        if local:
            entry["file"] = file_fingerprint(local)
        derived = str(_quiet(lambda: layer.customProperty("sigmai/derived_from", "")) or "")
        if derived:
            entry["derived_from"] = derived
        described.append(entry)
    try:
        from ..bridge_server import plugin_version

        sigmai_version = plugin_version()
    except Exception:
        sigmai_version = ""
    qgis_version = str(_quiet(imports["Qgis"].version) or "")
    project_path = str(_quiet(imports["QgsProject"].instance().fileName) or "")
    recipe = build_recipe(params, described, result, sigmai_version=sigmai_version, qgis_version=qgis_version,
                          project_path=project_path)
    text = recipe_to_json(recipe)
    _try(lambda: layout.setCustomProperty(RECIPE_PROPERTY, text))

    if output_path is not None and export_format == "png" and output_path.exists():
        try:
            from qgis.PyQt.QtGui import QImage  # type: ignore

            image = QImage(str(output_path))
            if not image.isNull():
                image.setText(RECIPE_PNG_KEY, text)
                if image.save(str(output_path), "PNG"):
                    recipe["embedded_in_output"] = True
        except Exception as exc:
            notes.append(f"A receita não pôde ser gravada nos metadados do PNG: {exc}")

    recipe_path_text = as_text(params, "recipe_path", default="", label="recipe_path").strip()
    if recipe_path_text:
        recipe_path = _resolve_output_path({"output_path": recipe_path_text})
        if recipe_path is None or recipe_path.suffix.lower() != ".json":
            raise CompositionError(f"recipe_path precisa ser um caminho absoluto terminado em .json: {recipe_path_text!r}.")
        recipe_path.write_text(text, encoding="utf-8")
        recipe["recipe_path"] = str(recipe_path)
    return recipe


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


def _resolve_figure_width(params: dict[str, Any]) -> float | None:
    """Largura final da figura em mm, de ``figure_width_mm`` ou ``journal_column``; ``None`` sem preset."""
    width = as_number(params, "figure_width_mm", None, minimum=30.0, maximum=600.0, label="figure_width_mm")
    column = as_text(params, "journal_column", default="", label="journal_column").strip().lower().replace("-", "_").replace(" ", "_")
    if column:
        aliases = {"simple": "single", "simples": "single", "uma": "single", "1": "single", "dupla": "double", "2": "double",
                   "duas": "double", "1.5": "one_and_half", "1,5": "one_and_half", "meia": "one_and_half"}
        column = aliases.get(column, column)
        if column not in JOURNAL_COLUMNS:
            raise CompositionError(
                f"journal_column desconhecido: {params.get('journal_column')!r}. Aceitos: "
                + ", ".join(f"{name} ({mm:g} mm)" for name, mm in JOURNAL_COLUMNS.items())
                + ". Se a revista pede outra largura, passe figure_width_mm."
            )
        if width is None:
            width = JOURNAL_COLUMNS[column]
    return float(width) if width is not None else None


def _solve_figure_page(
    width: float, height: float | None, max_height: float, margin_mm: Any, extent: Any, layout_request: dict[str, Any],
) -> tuple[PageSpec, LayoutPlan]:
    """Página da figura: largura fixa; altura dada ou a que casa o quadro com o recorte."""
    def solve(h: float) -> tuple[PageSpec, LayoutPlan]:
        spec = resolve_page({"width_mm": width, "height_mm": h, "name": "figura"}, None, margin_mm)
        return spec, solve_layout(**{**layout_request, "page": spec})

    if height is not None:
        try:
            return solve(float(height))
        except ValueError as exc:
            raise CompositionError(str(exc)) from exc
    data_aspect = (extent.width() / extent.height()) if extent.height() > 0 else 1.0
    best: tuple[float, PageSpec, LayoutPlan] | None = None
    h = max(20.0, width * 0.5)
    ceiling = min(float(max_height), width * 2.6)
    while h <= ceiling + 1e-6:
        try:
            spec, plan = solve(h)
            frame = plan.map_frame()
            if frame.height > 0:
                mismatch = abs(math.log((frame.width / frame.height) / data_aspect))
                if best is None or mismatch < best[0] - 1e-9:
                    best = (mismatch, spec, plan)
        except ValueError:
            pass
        h += 2.0
    if best is None:
        raise CompositionError(
            f"Não há altura entre {width * 0.5:g} e {ceiling:g} mm em que um layout caiba numa figura de {width:g} mm de "
            "largura. Use uma coluna mais larga (journal_column='double'), desative itens de apoio ou aumente figure_max_height_mm."
        )
    return best[1], best[2]


def _better_arrangement(extent: Any, frame: Any, plan: LayoutPlan, layout_request: dict[str, Any]) -> str | None:
    """O arranjo oposto (coluna lateral × faixa inferior), se nele o quadro aproveitar o recorte ≥ 12% melhor."""
    if plan.arrangement not in ("coluna_lateral", "faixa_inferior"):
        return None
    if extent.height() <= 0 or extent.width() <= 0 or frame.height <= 0 or frame.width <= 0:
        return None
    other = "faixa_inferior" if plan.arrangement == "coluna_lateral" else "coluna_lateral"
    try:
        alternative = solve_layout(**{**layout_request, "arrangement": other}).map_frame()
    except Exception:
        return None
    if alternative.width <= 0 or alternative.height <= 0:
        return None
    current_factor = max(extent.width() / frame.width, extent.height() / frame.height)
    alternative_factor = max(extent.width() / alternative.width, extent.height() / alternative.height)
    if alternative_factor <= 0:
        return None
    return other if current_factor / alternative_factor >= LAYOUT_SWITCH_GAIN else None


def _better_orientation(
    extent: Any, frame: Any, page: PageSpec, template: str, layout_request: dict[str, Any], gutter: float,
) -> str | None:
    """A orientação oposta, se nela o quadro aproveitar o recorte ≥ 12% melhor; senão ``None``."""
    if extent.height() <= 0 or frame.height <= 0 or frame.width <= 0:
        return None
    flipped = "portrait" if page.orientation == "landscape" else "landscape"
    try:
        alt_page = resolve_page(
            page.name if page.name.upper() in PAGE_SIZES else
            {"width_mm": page.height_mm, "height_mm": page.width_mm, "name": page.name},
            flipped,
            {"top": page.margin_top_mm, "right": page.margin_right_mm, "bottom": page.margin_bottom_mm, "left": page.margin_left_mm},
        )
        alternative = solve_layout(**{**layout_request, "page": alt_page}).map_frame()
    except Exception:
        return None
    current_factor = max(extent.width() / frame.width, extent.height() / frame.height)
    alternative_factor = max(extent.width() / alternative.width, extent.height() / alternative.height)
    if alternative_factor <= 0:
        return None
    return flipped if current_factor / alternative_factor >= LAYOUT_SWITCH_GAIN else None


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
    if gain < LAYOUT_SWITCH_GAIN:  # abaixo disso o ganho não paga o ruído do aviso
        return []

    label = "retrato" if flipped == "portrait" else "paisagem"
    return [
        f"Os dados têm proporção {data_aspect:.2f} e o quadro {frame.width / frame.height:.2f}. "
        f"Em {label} o mapa caberia numa escala cerca de {gain:.1f}x maior, aproveitando melhor a folha."
    ]


#: Formatos raster em que a auditoria consegue medir tinta no arquivo exportado.
_RASTER_AUDIT_SUFFIXES = (".png", ".tif", ".tiff", ".jpg", ".jpeg")


def audit_layout(
    layout: Any,
    *,
    page: PageSpec | None = None,
    output_path: str | None = None,
    data_extent: dict[str, float] | None = None,
    map_frame: Rect | None = None,
    print_width_mm: float | None = None,
    collect_labels: bool = True,
) -> dict[str, Any]:
    """Observa um layout e roda o regulamento cartográfico contra ele.

    Além da estrutura do layout, a observação ganha o que só a renderização
    mostra: a tinta do quadro (inteira e em grade 3x3), a tinta em volta de
    cada item desenhado sobre o quadro (para distinguir uma rosa dos ventos
    num canto vazio de uma sobre os dados) e os rótulos que o motor do QGIS
    descartou. ``print_width_mm`` diz em que largura a figura vai ser
    impressa, quando se sabe, para que as fontes sejam julgadas nessa
    largura e não na página.
    """
    from .inspector import (
        collect_label_results, measure_ink_fraction, measure_ink_grid, measure_surroundings_ink, observe_layout,
    )

    raster_path = output_path if output_path and str(output_path).lower().endswith(_RASTER_AUDIT_SUFFIXES) else None
    page_mm = (page.width_mm, page.height_mm) if page is not None else None
    ink = grid = None
    if raster_path and map_frame is not None and page_mm is not None:
        ink = measure_ink_fraction(raster_path, map_frame.to_dict(), page_mm)
        grid = measure_ink_grid(raster_path, map_frame.to_dict(), page_mm)

    # Rótulos descartados, por quadro. A chave é o id que a observação vai
    # usar: o id do QGIS quando existe, senão o sintético ("map#1", "map#2")
    # gerado pela mesma regra e na mesma ordem do inspetor.
    label_results: dict[str, dict[str, Any]] = {}
    if collect_labels:
        try:
            counter = 0
            for item in layout.items():
                if type(item).__name__ != "QgsLayoutItemMap":
                    continue
                item_id = str(item.id() or "")
                if not item_id:
                    counter += 1
                    item_id = f"map#{counter}"
                collected = collect_label_results(item)
                if collected is not None:
                    label_results[item_id] = collected
        except Exception:
            label_results = {}

    observation = observe_layout(
        layout,
        output_path=output_path,
        page_spec=page,
        data_extent=data_extent,
        ink_fraction=ink,
        ink_grid=grid,
        label_results=label_results or None,
        print_width_mm=print_width_mm,
    )

    # Tinta em volta dos itens desenhados sobre o quadro do mapa — só faz
    # sentido com o raster e com um quadro conhecido.
    if raster_path and page_mm is not None:
        frame_entry = next((i for i in observation.get("items", []) if i.get("role") == "map"), None)
        if frame_entry is not None:
            frame_rect = {k: float(frame_entry.get(k, 0.0)) for k in ("x", "y", "width", "height")}
            for item in observation.get("items", []):
                if item is frame_entry or item.get("role") in ("map", "background"):
                    continue
                rect = {k: float(item.get(k, 0.0)) for k in ("x", "y", "width", "height")}
                overlap_w = min(rect["x"] + rect["width"], frame_rect["x"] + frame_rect["width"]) - max(rect["x"], frame_rect["x"])
                overlap_h = min(rect["y"] + rect["height"], frame_rect["y"] + frame_rect["height"]) - max(rect["y"], frame_rect["y"])
                if overlap_w > 0.5 and overlap_h > 0.5:
                    ring = measure_surroundings_ink(raster_path, rect, frame_rect, page_mm)
                    if ring is not None:
                        item["surroundings_ink_fraction"] = ring

    report = evaluate(observation)
    report["observation"] = observation
    return report


def _reject_if_audit_found_blank_output(audit: dict[str, Any]) -> None:
    """A ferramenta não pode contradizer o próprio laudo.

    CART062 (quadro em branco) e CART063 (arquivo não gravado ou pequeno
    demais para ter conteúdo) são o modo de falha mais perigoso do
    regulamento — todo código de retorno do QGIS diz sucesso mesmo assim.
    ``margin_mm: 200`` numa página A5 chegou a exportar um PNG branco, a
    própria auditoria marcava CART063 "provável exportação vazia" com
    severidade ``error``, e ``compose_map`` devolvia sucesso do mesmo jeito.
    Esta função é pura (só lê o dicionário do laudo) para poder ser testada
    sem PyQGIS: veja ``tests/test_parameter_validation.py``.
    """
    blank_output_failures = [
        entry for entry in audit.get("blocking_issues", [])
        if entry.get("id") in _BLANK_OUTPUT_RULES
    ]
    if not blank_output_failures:
        return
    detalhe = " ".join(f"[{entry['id']}] {entry['detail_pt']}" for entry in blank_output_failures)
    raise CompositionError(
        "A auditoria reprovou a própria exportação, então compose_map não pode devolver isto "
        f"como sucesso: {detalhe} Ajuste extensão, margem, camadas visíveis ou permissão de "
        "escrita e gere o mapa novamente."
    )


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


#: Nome legível de cada item gerado, só para a mensagem de recusa do defeito
#: 2 apontar "o título"/"o subtítulo" em vez do id interno do item.
_FIELD_LABELS_PT: dict[str, str] = {
    "title": "título",
    "subtitle": "subtítulo",
    "panel_caption_a": "legenda do painel A",
    "panel_caption_b": "legenda do painel B",
}


def _measure_text_mm_fn(layout: Any, imports: dict[str, Any], bold: bool) -> Any:
    """Fecha uma função (texto, pt) -> largura em mm, usando QgsTextRenderer.

    A medição é feita num QgsRenderContext próprio, a um DPI fixo (300):
    testado empiricamente, a razão pixel/mm que QgsTextRenderer.textWidth
    devolve é a mesma independente do DPI do contexto (só muda o
    arredondamento de hinting), então um DPI alto e fixo aqui — em vez do DPI
    de exportação do mapa, que pode nem ter sido decidido ainda neste ponto
    da composição — dá uma medição estável e consistente entre chamadas.
    """
    context = imports["QgsLayoutUtils"].createRenderContextForLayout(layout, None, 300.0)
    text_format = imports["QgsTextFormat"]()

    def measure(candidate: str, size_pt: float) -> float:
        font = imports["QFont"]()
        font.setPointSizeF(float(size_pt))
        font.setBold(bool(bold))
        text_format.setFont(font)
        text_format.setSize(float(size_pt))
        try:
            text_format.setSizeUnit(qt_enum(imports["Qgis"], "RenderUnit", "Points"))
        except Exception:
            pass
        pixels = imports["QgsTextRenderer"].textWidth(context, text_format, [candidate])
        return float(pixels) * 25.4 / 300.0

    return measure


def _fit_label_text(
    item_id: str, text: str, rect: Rect, font_pt: float,
    layout: Any, imports: dict[str, Any], bold: bool, notes: list[str] | None,
) -> tuple[str, float]:
    """Defeito 2: nunca deixa um texto gerado ser cortado em silêncio.

    QgsLayoutItemLabel não recusa nem quebra texto largo demais para a caixa
    — desenha a linha inteira, que sai para os dois lados e é cortada pela
    borda da página, sem nenhum aviso. fit_text (textfit.py) resolve isso
    reduzindo a fonte (com piso — regra CART044) e/ou quebrando em pontos
    seguros; aqui só conectamos a medição real (QgsTextRenderer, via
    _measure_text_mm_fn) e viramos a recusa numa CompositionError com o nome
    do campo, em vez de deixar a mensagem genérica do textfit.py.
    """
    try:
        result = fit_text(text, rect.width, float(font_pt), _measure_text_mm_fn(layout, imports, bold))
    except TextTooLongError as exc:
        nome_campo = _FIELD_LABELS_PT.get(item_id, item_id)
        raise CompositionError(
            f"O {nome_campo} não cabe no espaço reservado ({rect.width:.0f} mm de largura) nem "
            f"reduzindo a fonte até o piso de {MIN_FONT_PT:g}pt (regra CART044) nem quebrando linha "
            f"nos pontos de quebra seguros disponíveis. Nesse tamanho de fonte, cerca de "
            f"{exc.max_chars} caracteres cabem nessa largura; encurte o texto, aumente a página ou "
            "reduza a margem."
        ) from exc
    if notes is not None:
        nome_campo = _FIELD_LABELS_PT.get(item_id, item_id)
        if result.shrunk:
            notes.append(
                f"O {nome_campo} foi reduzido de {font_pt:g}pt para {result.font_pt:g}pt para caber "
                f"na largura reservada ({rect.width:.0f} mm), sem passar do piso de {MIN_FONT_PT:g}pt "
                "da regra CART044."
            )
        if result.wrapped:
            notes.append(
                f"O {nome_campo} foi quebrado em {len(result.lines)} linhas: não havia espaço em "
                "branco suficiente para o QGIS quebrar sozinho (escrita sem espaço entre palavras, "
                "ou uma única palavra larga demais para a caixa), e o texto não cabia numa linha só."
            )
    return result.text, result.font_pt


def _add_label(
    layout: Any, item_id: str, text: str, rect: Rect, font_pt: float,
    imports: dict[str, Any], mm: Any, *, bold: bool = False, align: str = "left",
    notes: list[str] | None = None, fit: bool = False,
) -> Any:
    display_text = text
    resolved_font_pt = float(font_pt)
    if fit and text and text.strip():
        display_text, resolved_font_pt = _fit_label_text(item_id, text, rect, font_pt, layout, imports, bold, notes)

    label = imports["QgsLayoutItemLabel"](layout)
    label.setId(item_id)
    label.setText(display_text)
    font = imports["QFont"]()
    font.setPointSizeF(float(resolved_font_pt))
    font.setBold(bool(bold))
    try:
        label.setFont(font)
    except Exception:
        pass
    # QGIS ≥3.24: a fonte efetiva vem do QgsTextFormat.
    try:
        text_format = label.textFormat()
        text_format.setFont(font)
        text_format.setSize(float(resolved_font_pt))
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


def _is_label_only(layer: Any) -> bool:
    try:
        renderer = layer.renderer()
        return renderer is not None and str(renderer.type()) == "nullSymbol"
    except Exception:
        return False


#: Caractere de quebra de linha das entradas da legenda (QgsLayoutItemLegend
#: não quebra sozinho; ``setWrapString`` quebra onde este caractere aparece).
LEGEND_WRAP = "\u2028"


#: Largura reservada, em mm, para o símbolo e os espaçamentos à esquerda do
#: texto de uma entrada da legenda.
LEGEND_SYMBOL_BAND_MM = 14.0


def _legend_columns(plan: LayoutPlan, entries: int) -> int:
    slot = plan.slots.get("legend")
    return 2 if (slot is not None and slot.aspect > 1.6 and entries > 3) else 1


def _wrap_legend_label(
    layout: Any, imports: dict[str, Any], name: str, source: str, plan: LayoutPlan, columns: int = 1,
) -> str:
    """``nome`` + fonte entre parênteses, quebrados em linhas que cabem na coluna da legenda.

    O nome também é quebrado: numa figura de 175 mm a coluna da legenda tem
    ~45 mm e "Limite estadual do Piauí" saía cortado na borda da caixa — a
    emulação da 1.1.0 mostrou o texto truncado que nenhuma regra acusava.
    """
    slot = plan.slots.get("legend")
    slot_width = slot.width if slot is not None else 60.0
    available = max(20.0, slot_width / max(1, columns) - LEGEND_SYMBOL_BAND_MM)
    size_pt = float(plan.fonts.get("legend", 8.0))
    try:
        measure = _measure_text_mm_fn(layout, imports, bold=False)
    except Exception:
        def measure(text: str, _pt: float) -> float:  # ~0,5 em por caractere
            return len(text) * size_pt * 0.3528 * 0.5

    def wrap(text: str) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and measure(candidate, size_pt) > available:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    lines = wrap(name) or [name]
    if source:
        lines.extend(wrap(f"({source})"))
    return LEGEND_WRAP.join(lines)


def _legend_content_size_mm(legend: Any) -> tuple[float, float] | None:
    """Tamanho mínimo (mm) que o conteúdo da legenda precisa para ser desenhado inteiro."""
    try:
        from qgis.core import QgsLegendRenderer  # type: ignore

        size = QgsLegendRenderer(legend.model(), legend.legendSettings()).minimumSize()
        return float(size.width()), float(size.height())
    except Exception:
        return None


def _set_legend_font(legend: Any, imports: dict[str, Any], size_pt: float) -> None:
    font = imports["QFont"]()
    font.setPointSizeF(float(size_pt))
    from qgis.core import QgsLegendStyle  # type: ignore

    for style_name in ("Title", "Group", "Subgroup", "SymbolLabel"):
        legend.setStyleFont(qt_enum(QgsLegendStyle, "Style", style_name), font)


def _fit_legend_in_box(
    legend: Any, slot: Rect, plan: LayoutPlan, layout: Any, imports: dict[str, Any], layer_sources: dict[str, str],
    columns: int, notes: list[str] | None,
) -> None:
    """Faz o conteúdo da legenda caber na caixa: fonte menor, depois sem as fontes por camada.

    ``QgsLayoutItemLegend`` não avisa quando o conteúdo passa da caixa: corta
    o texto na borda e desenha por cima do que vier abaixo. Numa figura de
    coluna simples (85 mm) a caixa tem ~26 mm de altura, e duas entradas com
    fonte por camada já não cabem — a emulação da 1.1.0 mostrou "(IBGE, 2024)"
    sobre a linha de crédito. A medida vem de ``QgsLegendRenderer.minimumSize``.
    """
    tolerance = 0.5
    content = _legend_content_size_mm(legend)
    if content is None:
        return

    def fits() -> bool:
        c = _legend_content_size_mm(legend)
        return c is None or (c[0] <= slot.width + tolerance and c[1] <= slot.height + tolerance)

    if fits():
        return
    size_pt = float(plan.fonts.get("legend", 8.0))
    while not fits() and size_pt - 0.5 >= MIN_FONT_PT:
        size_pt -= 0.5
        try:
            _set_legend_font(legend, imports, size_pt)
        except Exception:
            return
    if fits():
        if notes is not None:
            notes.append(f"Fonte da legenda reduzida para {size_pt:g} pt para o conteúdo caber na caixa.")
        return
    # Ainda não cabe: as fontes por camada saem da legenda (continuam na
    # linha de crédito e na receita); os nomes continuam quebrados na coluna.
    dropped = False
    try:
        for node in legend.model().rootGroup().findLayers():
            layer = node.layer()
            if layer is None or not node.customProperty("legend/title-label", ""):
                continue
            label = _wrap_legend_label(layout, imports, layer.name(), "", plan, columns)
            if label != layer.name():
                node.setCustomProperty("legend/title-label", label)
            else:
                # Propriedade vazia não devolve o nome da camada: some o rótulo.
                node.removeCustomProperty("legend/title-label")
            legend.model().refreshLayerLegend(node)
            dropped = True
        legend.updateLegend()
    except Exception:
        pass
    # Sem as fontes por camada sobra espaço: a fonte volta a crescer até o
    # corpo planejado enquanto couber — 7 pt sem fontes é melhor que 6 pt.
    if dropped and fits():
        planned = float(plan.fonts.get("legend", 8.0))
        while size_pt + 0.5 <= planned:
            try:
                _set_legend_font(legend, imports, size_pt + 0.5)
            except Exception:
                break
            if fits():
                size_pt += 0.5
            else:
                try:
                    _set_legend_font(legend, imports, size_pt)
                except Exception:
                    pass
                break
    if notes is not None:
        content = _legend_content_size_mm(legend) or content
        if fits():
            if dropped:
                notes.append(
                    "As fontes por camada não couberam na legenda e ficaram só na linha de crédito "
                    f"(fonte da legenda em {size_pt:g} pt)."
                )
        else:
            notes.append(
                f"A legenda precisa de {content[0]:.0f} x {content[1]:.0f} mm e a caixa tem "
                f"{slot.width:.0f} x {slot.height:.0f} mm mesmo a {size_pt:g} pt: reduza o número de camadas na "
                "legenda, encurte os nomes ou use uma página maior."
            )


def _add_legend(
    layout: Any, map_item: Any, layers: list[Any], plan: LayoutPlan,
    params: dict[str, Any], imports: dict[str, Any], mm: Any, map_language: str = "pt-BR",
    layer_sources: dict[str, str] | None = None, notes: list[str] | None = None,
) -> Any:
    legend = imports["QgsLayoutItemLegend"](layout)
    legend.setId("legend")
    legend.setTitle(as_text(params, "legend_title", default=maptext(map_language, "legenda_padrao"), label="legend_title"))
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
        legend_layers = [layer for layer in layers if not _is_label_only(layer)]
        columns = _legend_columns(plan, len(legend_layers))
        for layer in legend_layers:
            # Camada só-de-rótulo (sem símbolo) não tem o que mostrar na
            # legenda; uma entrada vazia com o nome "Nomes — Piauí" confunde.
            node = root.addLayer(layer)
            # Procedência na própria entrada: "Municípios (IBGE, 2024)". O
            # rótulo da entrada de símbolo único é fixado quando o nó é
            # criado, por isso a propriedade vai ANTES de updateLegend — e
            # sem renomear a camada do projeto.
            source = (layer_sources or {}).get(layer.id(), "")
            if node is not None:
                try:
                    # A fonte vai numa segunda linha, e o nome comprido é
                    # quebrado na largura da coluna: "IBGE, Malha Municipal
                    # 2024" não cabe ao lado do nome numa coluna de 50 mm.
                    label = _wrap_legend_label(layout, imports, layer.name(), source, plan, columns)
                    if label != layer.name():
                        node.setCustomProperty("legend/title-label", label)
                        # O nó de símbolo já foi criado em addLayer com o nome
                        # antigo; a propriedade só vale depois de recriá-lo.
                        legend.model().refreshLayerLegend(node)
                        legend.setWrapString(LEGEND_WRAP)
                except Exception:
                    pass
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
        legend.setColumnCount(_legend_columns(plan, max(1, len([l for l in layers if not _is_label_only(l)]))))
        legend.setSplitLayer(True)
        legend.setEqualColumnWidth(True)
    except Exception:
        pass
    try:
        _set_legend_font(legend, imports, float(plan.fonts["legend"]))
    except Exception:
        pass
    _place(legend, slot, imports, mm)
    try:
        columns = _legend_columns(plan, max(1, len([l for l in layers if not _is_label_only(l)])))
        _fit_legend_in_box(legend, slot, plan, layout, imports, layer_sources or {}, columns, notes)
    except Exception:
        pass
    return legend


def _scalebar_number_format(imports: dict[str, Any], map_language: str) -> Any:
    """Formato numérico dos rótulos da barra na língua do mapa.

    Sem isto o QGIS formata pelo locale do processo: num mapa em português
    a barra saía "0  1,000  2,000 m" — separador de milhar inglês ao lado de
    uma escala numérica escrita "1:25.000". O separador vem de maptext.py, o
    mesmo da escala numérica.
    """
    try:
        from qgis.core import QgsBasicNumericFormat  # type: ignore

        fmt = QgsBasicNumericFormat()
        thousands = maptext(map_language, "separador_milhar")
        fmt.setShowThousandsSeparator(bool(thousands))
        if thousands:
            fmt.setThousandsSeparator(thousands[0])
        fmt.setDecimalSeparator("," if thousands == "." else ".")
        fmt.setShowTrailingZeros(False)
        return fmt
    except Exception:
        return None


def _add_scalebar(
    layout: Any, map_item: Any, spec: Any, plan: LayoutPlan, imports: dict[str, Any], mm: Any, page: PageSpec | None = None,
    map_language: str = "pt-BR",
) -> Any:
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
    number_format = _scalebar_number_format(imports, map_language)
    if number_format is not None:
        _try(lambda: bar.setNumericFormat(number_format))
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
    # A altura do item de barra é própria (segmento + espaço até o rótulo +
    # texto + folga da caixa) e ignora a faixa reservada: com os padrões do
    # QGIS ela dá ~10,6 mm, e numa faixa de 7 mm (A5 paisagem, template
    # minimalista) o excedente invadia o rodapé — CART042 acusava a barra
    # sobre a linha de crédito. Segmento e folgas são derivados da faixa.
    font_pt = max(6.0, float(plan.fonts["scale_text"]) - 1.0)
    text_h = font_pt * 0.3528 * 1.25
    box_space = 0.5
    label_space = 1.2
    segment_h = max(1.2, min(3.0, slot.height - text_h - label_space - 2 * box_space))
    _try(lambda: bar.setBoxContentSpace(box_space))
    _try(lambda: bar.setLabelBarSpace(label_space))
    _try(lambda: bar.setHeight(segment_h))
    _place(bar, slot, imports, mm)
    try:
        bar.update()
        # O item de barra cresce para caber os rótulos. Se estourar a faixa
        # reservada, recua para a esquerda em vez de invadir a margem (CART041).
        actual = bar.sizeWithUnits()
        bar_x, bar_y = slot.x, slot.y
        vertical_overflow = float(actual.height()) - slot.height
        if vertical_overflow > 0.1:
            # O que ainda sobrar sobe para dentro da calha acima da faixa, que
            # é folga entre itens, nunca desce sobre o rodapé.
            bar_y = slot.y - vertical_overflow
        overflow = float(actual.width()) - slot.width
        if overflow > 0.1 and page is not None:
            # Se ainda assim transbordar, empurra para a ESQUERDA apenas até o
            # limite da área útil — nunca para dentro do quadro do mapa, que
            # fica à esquerda da faixa de apoio. Mover para lá trocava um aviso
            # de margem por uma sobreposição sobre o mapa, que é pior.
            right_edge = page.content_x_mm + page.content_width_mm
            new_x = min(slot.x, right_edge - float(actual.width()))
            new_x = max(new_x, slot.x - overflow)
            bar_x = max(page.content_x_mm, new_x)
        if (bar_x, bar_y) != (slot.x, slot.y):
            bar.attemptMove(imports["QgsLayoutPoint"](bar_x, bar_y, mm))
    except Exception:
        pass
    return bar


def _add_north_arrow(
    layout: Any, map_item: Any, rect: Rect, imports: dict[str, Any], mm: Any, notes: list[str],
    map_language: str = "pt-BR",
) -> str:
    svg_path = _find_north_arrow_svg(imports)
    if not svg_path:
        notes.append(
            "Nenhum SVG de norte foi encontrado na instalação do QGIS; usado rótulo de texto. "
            "Isso viola a regra CART025."
        )
        letra_norte = maptext(map_language, "norte_reserva")
        _add_label(layout, "north_arrow", letra_norte, rect, 14.0, imports, mm, bold=True, align="center")
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


def _empty_in_frame_advice(
    layers: list[Any], extent_layers: list[Any], fitted: Any, map_crs: Any, imports: dict[str, Any]
) -> list[str]:
    """Avisa sobre camadas que entram na legenda mas não aparecem no mapa.

    Pedir "o parque mostrando os municípios em volta" com um recorte apertado no
    parque pode deixar o município inteiro fora do quadro: a camada continua na
    legenda, e o leitor procura no mapa uma feição que não existe ali.
    """
    notes: list[str] = []
    subject_ids = {layer.id() for layer in extent_layers}
    frame = imports["QgsRectangle"](fitted.xmin, fitted.ymin, fitted.xmax, fitted.ymax)
    for layer in layers:
        if layer.id() in subject_ids or not hasattr(layer, "getFeatures"):
            continue
        try:
            transform = imports["QgsCoordinateTransform"](
                map_crs, layer.crs(), imports["QgsProject"].instance()
            )
            local_frame = transform.transformBoundingBox(frame)
            request = imports["QgsFeatureRequest"]().setFilterRect(local_frame).setLimit(1)
            request.setNoAttributes()
            if next(layer.getFeatures(request), None) is None:
                if _is_label_only(layer):
                    notes.append(
                        f"A camada de rótulos {layer.name()!r} não tem nenhum ponto dentro do recorte: "
                        "nenhum nome dela vai aparecer no mapa. Aumente margin_percent, passe extra_labels "
                        "com coordenadas dentro do recorte ou tire-a de layer_ids."
                    )
                else:
                    notes.append(
                        f"A camada {layer.name()!r} não tem nenhuma feição dentro do recorte: "
                        "ela vai aparecer na legenda e não no mapa. Tire-a de layer_ids, "
                        "aumente margin_percent ou escolha outra camada de contexto."
                    )
        except Exception:
            continue
    return notes


def _field_has_values(layer: Any, field: str) -> bool:
    """O campo tem ao menos um valor não nulo e não vazio?

    ``uniqueValues`` percorre o provedor e para cedo; é barato mesmo em camadas
    grandes, e respeita o subsetString aplicado à camada.
    """
    try:
        index = layer.fields().indexFromName(field)
        if index < 0:
            return False
        for value in layer.uniqueValues(index, limit=25):
            if value is None:
                continue
            texto = str(value).strip()
            if texto and texto.upper() != "NULL":
                return True
        return False
    except Exception:
        # Provedor sem uniqueValues: na dúvida, deixa passar em vez de recusar
        # um mapa que talvez estivesse correto.
        return True


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

    requested_id = as_text(params, "label_layer_id", default="", label="label_layer_id").strip()
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

    # Existir não basta: um campo presente e inteiramente vazio produz um mapa
    # sem um único rótulo, enquanto a resposta anuncia rótulos criados. Foi o
    # que aconteceu com o campo 'Name' de um KML do CNUC, cujo nome real mora
    # em 'Nome_UC'.
    if not _field_has_values(target, field):
        preenchidos = [
            item.name() for item in target.fields()
            if item.name() != field and _field_has_values(target, item.name())
        ]
        near = difflib.get_close_matches(field, preenchidos, n=3, cutoff=0.0)
        sugestao = f" Campos com conteúdo nesta camada: {', '.join(near or preenchidos[:6]) or 'nenhum'}."
        raise CompositionError(
            f"O campo {field!r} existe em {target.name()!r} mas está vazio em todas as feições; "
            f"rotular por ele produziria um mapa sem nenhum rótulo.{sugestao}"
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
        if geometry == "Polygon":
            # Polígono cortado pela moldura: o rótulo vai para o centroide da
            # PARTE VISÍVEL, não do polígono inteiro — senão o motor calcula o
            # centroide fora do quadro e descarta o rótulo em silêncio
            # (CART068 acusa o que ainda assim não couber).
            settings.centroidWhole = False
            settings.centroidInside = True
    except Exception:
        pass

    # label_font_size fora de uma faixa legível: abaixo de 3pt o QGIS não
    # desenha nada (texto menor que a resolução de descarte do PAL), e acima
    # de 72pt o rótulo mais comum não cabe em lugar nenhum do quadro — os dois
    # casos faziam a resposta anunciar "rotulado" sem um único rótulo visível.
    label_font_size = as_number(
        params, "label_font_size", default=plan.fonts["legend"],
        minimum=3.0, maximum=72.0, label="label_font_size",
    )
    text_format = QgsTextFormat()
    font = imports["QFont"]()
    font.setPointSizeF(float(label_font_size))
    text_format.setFont(font)
    text_format.setSize(float(label_font_size))
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


def _panel_label(index: int) -> str:
    """Nome do painel extra nas mensagens: o primeiro continua 'second_map'."""
    return "second_map" if index == 0 else f"panels[{index}]"


def _plan_comparison(
    spec: dict[str, Any], params: dict[str, Any], plan: LayoutPlan, map_crs: Any, imports: dict[str, Any],
    slot: str = "map_2", label: str = "second_map",
) -> dict[str, Any]:
    """Resolve camadas e recorte de um painel extra, sem ainda desenhar nada."""
    layers = _resolve_layer_ids(spec, imports, label)
    if not layers:
        raise CompositionError(f"{label} precisa de layer_ids com ao menos uma camada.")

    extent_layers = _subject_subset(layers, as_text(spec, "subject_layer_id", default="", label=f"{label}.subject_layer_id"))

    # margin_percent do painel é opcional; sem ele, herda o margin_percent do
    # mapa principal (já validado). float(spec.get(..., params.get(...))) cru
    # estourava ValueError sem contexto quando "muita" chegava como texto.
    main_margin = as_number(params, "margin_percent", default=5.0, minimum=0.0, maximum=100.0, label="margin_percent")
    frame = plan.slots[slot]
    extent = _combined_extent(extent_layers, map_crs, imports)
    fitted = fit_extent_to_frame(
        extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum(),
        frame.width, frame.height,
        margin_percent=as_number(
            spec, "margin_percent", default=main_margin, minimum=0.0, maximum=100.0, label=f"{label}.margin_percent",
        ),
        snap_to_round_scale=as_flag(params, "round_scale", True)[0],
        map_units_per_metre=_map_units_per_metre(map_crs, extent, imports),
    )
    return {"layers": layers, "fitted": fitted, "frame": frame, "spec": spec, "slot": slot, "label": label}


def _equalisation_cost_advice(before: tuple[int, int], shared: int) -> list[str]:
    """Avisa quando igualar as escalas esvazia um dos painéis.

    Igualar é honesto: dois painéis em escalas diferentes convidam a uma
    comparação de tamanho que não se sustenta. Mas honesto não é o mesmo que
    útil. Ao comparar um parque de 10.000 ha com um estado inteiro, a escala
    comum é a do estado, e o parque vira um ponto invisível num quadro em
    branco — o painel cumpre a regra e não informa nada. Quem pediu precisa
    saber disso para escolher entre a comparação honesta e um inserto de
    localização, que é o elemento certo quando as ordens de grandeza são
    incomparáveis.
    """
    notes: list[str] = []
    for index, original in enumerate(before, start=1):
        if original <= 0 or shared <= 0:
            continue
        # A área ocupada cai com o QUADRADO da razão entre as escalas: abrir a
        # escala dez vezes deixa o assunto com um centésimo do quadro.
        fracao_area = (float(original) / float(shared)) ** 2
        if fracao_area < 0.02:
            notes.append(
                f"Depois de igualar as escalas, o assunto do painel {index} ocupa cerca de "
                f"{fracao_area * 100:.1f}% do quadro — visualmente, um quadro vazio. As duas "
                "ordens de grandeza são distantes demais para uma comparação lado a lado: "
                "passe comparison_same_scale=false para cada painel anunciar a sua escala, "
                "ou troque o segundo painel por include_inset=true, que é o elemento próprio "
                "para situar um recorte pequeno dentro de uma área grande."
            )
    return notes


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


#: Letras das legendas de painel numa figura com três ou mais quadros.
PANEL_LETTERS = "abcdefgh"


def _build_comparison_map(
    layout: Any, comparison: dict[str, Any], params: dict[str, Any], plan: LayoutPlan,
    map_crs: Any, imports: dict[str, Any], mm: Any, notes: list[str], grid_style: str = "solid",
    map_language: str = "pt-BR", index: int = 0, total: int = 2,
) -> Any:
    """Desenha um quadro extra e as legendas de painel.

    A regra que sustenta o conjunto é a escala: painéis em escalas diferentes
    convidam a uma comparação visual que não se sustenta, porque o mesmo
    tamanho no papel passa a significar tamanhos distintos no terreno. Por isso
    o padrão é igualar — e, quando não se iguala, dizer isso no laudo.

    ``index`` é a posição do painel extra (0 = o antigo second_map, que
    mantém o id ``comparison_map``); ``total`` é o número de quadros na folha.
    Com dois quadros as legendas são "Painel A/B"; com três ou mais, "(a)",
    "(b)", "(c)"…, como numa figura de artigo.
    """
    frame = comparison["frame"]
    fitted = comparison["fitted"]
    second = imports["QgsLayoutItemMap"](layout)
    second.setId("comparison_map" if index == 0 else f"panel_map_{index + 2}")
    layout.addLayoutItem(second)
    _place(second, frame, imports, mm)
    second.setCrs(map_crs)
    second.setLayers(comparison["layers"])
    second.zoomToExtent(imports["QgsRectangle"](fitted.xmin, fitted.ymin, fitted.xmax, fitted.ymax))
    second.setFrameEnabled(True)
    # grid_style já validado por compose_map; reaproveitado aqui em vez de ler
    # params.get("grid_style", "solid") de novo, que caía no padrão em
    # silêncio para um valor desconhecido.
    _apply_grid(second, fitted, map_crs, plan, imports, [], grid_style)
    _verify_placement(second, frame, second.id(), notes)

    # Sem panel_title os painéis recebem rótulos simétricos ("Painel A"/
    # "Painel B" na língua do mapa; "(a)", "(b)"… com três ou mais). Repetir
    # o título da folha sobre o painel da esquerda, como se fazia, punha o
    # mesmo texto duas vezes a 2 cm de distância e deixava a direita com um
    # rótulo genérico ao lado de um específico — o leitor lia hierarquia onde
    # só havia omissão.
    main_title = as_text(params, "panel_title", default="", label="panel_title").strip()
    own_title = as_text(comparison["spec"], "panel_title", default="", label=f"{comparison.get('label', 'second_map')}.panel_title").strip()
    if total == 2:
        left = main_title or maptext(map_language, "painel_a")
        right = own_title or maptext(map_language, "painel_b")
    else:
        left = f"({PANEL_LETTERS[0]})" + (f" {main_title}" if main_title else "")
        right = f"({PANEL_LETTERS[index + 1]})" + (f" {own_title}" if own_title else "")
    if comparison.get("per_panel_scale"):
        left = f"{left} — {_format_scale(comparison['main_scale'], map_language)}"
        right = f"{right} — {_format_scale(fitted.scale_denominator, map_language)}"
    captions = [(f"{comparison['slot']}_caption", f"panel_caption_{PANEL_LETTERS[index + 1]}", right)]
    if index == 0:
        captions.insert(0, ("map_caption", "panel_caption_a", left))
    for slot_name, item_id, text in captions:
        if slot_name in plan.slots:
            _add_label(layout, item_id, text, plan.slots[slot_name], plan.fonts["subtitle"],
                       imports, mm, bold=True, align="center", notes=notes, fit=True)

    second.refresh()
    return second


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

    # as_id_list recusa tipos que não são iteráveis de textos (int, bool,
    # dict) em vez de deixar "for item in requested" estourar TypeError
    # quando inset_layer_ids chega como um número solto.
    requested = as_id_list(params, "inset_layer_ids", allow_single=True, label="inset_layer_ids")
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
    overrides = _inset_style_overrides(inset_layers, layers)
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
    factor = max(2.0, float(as_number(params, "inset_zoom_factor", default=12.0, label="inset_zoom_factor")))
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
    context_layer_name = ""
    if widest is not None and widest.width() > fitted.width * 1.5:
        context = imports["QgsRectangle"](widest)
        context.grow(max(context.width(), context.height()) * 0.04)
        context_layer_name = next(
            (layer.name() for layer in inset_layers
             if (_layer_extent_in_crs(layer, map_crs, imports) or imports["QgsRectangle"]()).width() == widest.width()),
            "",
        )

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
    # A nota dizia "12x a largura do recorte" mesmo quando o inserto tinha sido
    # ajustado à extensão inteira da camada de contexto — e um assistente,
    # lendo isso, refez o mapa com um fator maior sem necessidade.
    if context_layer_name:
        notes.append(
            f"Inserto de localização ajustado à extensão inteira de {context_layer_name!r}, "
            "com o retângulo do recorte principal desenhado por cima (inset_zoom_factor não se aplica)."
        )
    else:
        notes.append(
            f"Inserto de localização com {factor:g}x a largura do recorte principal, "
            "com o retângulo do recorte desenhado por cima. Passe inset_layer_ids com um limite "
            "(estado, município) para que ele mostre esse limite inteiro."
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


#: Cinza neutro do inserto. Um localizador existe para que o retângulo vermelho
#: do recorte salte aos olhos; se o contexto vem no matiz aleatório que o QGIS
#: sorteou ao carregar a camada, o retângulo compete com um estado inteiro em
#: roxo saturado e deixa de localizar coisa alguma.
INSET_CONTEXT_FILL = "#E9E9E9"
INSET_CONTEXT_STROKE = "#9A9A9A"


def _neutral_style_override(layer: Any) -> str:
    """QML da camada com simbologia cinza e sem rótulos, sem alterá-la no projeto.

    O estilo é exportado a partir de um renderizador cinza aplicado por um
    instante e imediatamente desfeito: o override do item de layout precisa de
    um QML completo, e montá-lo à mão quebraria a cada versão do QGIS.
    """
    from qgis.PyQt.QtXml import QDomDocument  # type: ignore
    from qgis.core import (  # type: ignore
        Qgis,
        QgsFillSymbol,
        QgsLineSymbol,
        QgsMarkerSymbol,
        QgsSingleSymbolRenderer,
        QgsWkbTypes,
    )
    from .qtcompat import geometry_type

    original = layer.renderer()
    if original is None:
        return ""
    clone = original.clone()

    geometry = layer.geometryType()
    if geometry == geometry_type(Qgis, QgsWkbTypes, "Polygon"):
        symbol = QgsFillSymbol.createSimple({
            "color": INSET_CONTEXT_FILL,
            "outline_color": INSET_CONTEXT_STROKE,
            "outline_width": "0.25",
            "style": "solid",
        })
    elif geometry == geometry_type(Qgis, QgsWkbTypes, "Line"):
        symbol = QgsLineSymbol.createSimple({
            "line_color": INSET_CONTEXT_STROKE, "line_width": "0.25",
        })
    else:
        symbol = QgsMarkerSymbol.createSimple({
            "color": INSET_CONTEXT_FILL, "outline_color": INSET_CONTEXT_STROKE, "size": "1.4",
        })

    try:
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        document = QDomDocument()
        layer.exportNamedStyle(document)
        root = document.documentElement()
        root.setAttribute("labelsEnabled", "0")
        for tag in ("labeling", "labelling"):
            nodes = root.elementsByTagName(tag)
            while nodes.count():
                root.removeChild(nodes.at(0))
        return document.toString()
    finally:
        # O projeto do usuário não pode ficar cinza por causa de um inserto.
        layer.setRenderer(clone)
        layer.triggerRepaint()


def _inset_style_overrides(inset_layers: list[Any], main_layers: list[Any]) -> dict[str, str]:
    """Estilo do inserto: contexto em cinza, camadas do mapa sem rótulos.

    Uma camada que também aparece no mapa principal conserva a sua cor — é assim
    que o leitor reconhece a mesma feição nos dois quadros. Uma camada que só
    existe no inserto é pano de fundo e vai para o cinza.
    """
    main_ids = {layer.id() for layer in main_layers}
    overrides = dict(_labelless_style_overrides([layer for layer in inset_layers if layer.id() in main_ids]))
    for layer in inset_layers:
        if layer.id() in main_ids or not hasattr(layer, "renderer"):
            continue
        try:
            style = _neutral_style_override(layer)
        except Exception:
            continue
        if style:
            overrides[layer.id()] = style
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
    # dpi<=1 produzia uma imagem de poucos pixels sem avisar (dpi:1 gerava
    # 11x8 px); dpi>1200 arrisca estourar a memória do QGIS do usuário (dpi
    # 20000 numa A4 chega a ~990 milhões de pixels). integer=True porque
    # int(1.5) truncaria em silêncio o que o pedido não disse.
    dpi = as_number(params, "dpi", default=300, minimum=50, maximum=1200, integer=True, label="dpi")
    if export_format in ("png", "tif", "tiff", "jpg", "jpeg"):
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
