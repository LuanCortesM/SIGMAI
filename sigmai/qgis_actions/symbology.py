from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cartography.qtcompat import geometry_type as _geometry_type
from ..security import ensure_parent_exists, normalize_output_path, reject_existing_path_without_confirmation
from ..cartography.symbology import (
    PROPORTIONAL_OUTLINE_SHADE, STYLE_ORIGIN_USER, mark_style_origin, shade, size_legend_values, style_origin,
)
from ..validators import ValidationError, require_param
from .common import layer_type_name, project


def _imports() -> dict[str, Any]:
    try:
        from qgis.PyQt.QtCore import Qt  # type: ignore
        from qgis.PyQt.QtGui import QColor, QFont  # type: ignore
        from qgis.core import (  # type: ignore
            Qgis,
            QgsCategorizedSymbolRenderer,
            QgsFillSymbol,
            QgsGraduatedSymbolRenderer,
            QgsLineSymbol,
            QgsMarkerSymbol,
            QgsPalLayerSettings,
            QgsRendererCategory,
            QgsRendererRange,
            QgsSingleSymbolRenderer,
            QgsTextBufferSettings,
            QgsTextFormat,
            QgsVectorLayerSimpleLabeling,
            QgsWkbTypes,
        )
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc
    return {
        "Qgis": Qgis,
        "Qt": Qt,
        "QColor": QColor,
        "QFont": QFont,
        "QgsCategorizedSymbolRenderer": QgsCategorizedSymbolRenderer,
        "QgsFillSymbol": QgsFillSymbol,
        "QgsGraduatedSymbolRenderer": QgsGraduatedSymbolRenderer,
        "QgsLineSymbol": QgsLineSymbol,
        "QgsMarkerSymbol": QgsMarkerSymbol,
        "QgsPalLayerSettings": QgsPalLayerSettings,
        "QgsRendererCategory": QgsRendererCategory,
        "QgsRendererRange": QgsRendererRange,
        "QgsSingleSymbolRenderer": QgsSingleSymbolRenderer,
        "QgsTextBufferSettings": QgsTextBufferSettings,
        "QgsTextFormat": QgsTextFormat,
        "QgsVectorLayerSimpleLabeling": QgsVectorLayerSimpleLabeling,
        "QgsWkbTypes": QgsWkbTypes,
    }


def _layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_LAYER", "Layer is invalid.", {"layer_id": layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "This command requires a vector layer.", {"layer_id": layer_id})
    return layer


def _field_exists(layer: Any, field_name: str) -> bool:
    return layer.fields().indexOf(field_name) >= 0


def _opacity_param(params: dict[str, Any], key: str, default: float) -> float:
    return max(0.0, min(1.0, float(params.get(key, default))))


def _qcolor(hex_color: str, opacity: float):
    imports = _imports()
    color = imports["QColor"](hex_color)
    try:
        color.setAlphaF(max(0.0, min(1.0, float(opacity))))
    except Exception:
        pass
    return color


def _apply_fill_symbol_details(symbol: Any, fill: str, stroke: str, fill_opacity: float, stroke_opacity: float, stroke_width: float, outline_only: bool) -> None:
    imports = _imports()
    try:
        symbol_layer = symbol.symbolLayer(0)
    except Exception:
        return
    if symbol_layer is None:
        return
    fill_color = _qcolor(fill, 0.0 if outline_only else fill_opacity)
    stroke_color = _qcolor(stroke, stroke_opacity)
    for method_name, value in (
        ("setFillColor", fill_color),
        ("setStrokeColor", stroke_color),
        ("setStrokeWidth", float(stroke_width)),
    ):
        try:
            method = getattr(symbol_layer, method_name, None)
            if method is not None:
                method(value)
        except Exception:
            pass
    if outline_only:
        try:
            symbol_layer.setBrushStyle(imports["Qt"].NoBrush)
        except Exception:
            pass


def _symbol_for_layer(
    layer: Any,
    fill: str,
    stroke: str,
    stroke_width: float,
    fill_opacity: float = 1.0,
    stroke_opacity: float = 1.0,
    outline_only: bool = False,
    marker_size: float | None = None,
):
    imports = _imports()
    geometry_type = layer.geometryType()
    if geometry_type == _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Point"):
        properties = {"color": fill, "outline_color": stroke, "outline_width": str(stroke_width)}
        if marker_size is not None:
            properties["size"] = str(marker_size)
        if stroke_width <= 0:
            properties["outline_style"] = "no"
        return imports["QgsMarkerSymbol"].createSimple(properties)
    if geometry_type == _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Line"):
        return imports["QgsLineSymbol"].createSimple({"color": stroke, "line_width": str(stroke_width)})
    style = "no" if outline_only else "solid"
    symbol = imports["QgsFillSymbol"].createSimple({"color": fill, "style": style, "outline_color": stroke, "outline_width": str(stroke_width)})
    _apply_fill_symbol_details(symbol, fill, stroke, fill_opacity, stroke_opacity, stroke_width, outline_only)
    return symbol


def _set_marker_alphas(symbol: Any, params: dict[str, Any], imports: dict[str, Any]) -> None:
    """fill_opacity e stroke_opacity pedidos explicitamente valem para o marcador (o preenchimento e o contorno)."""
    marker = symbol.symbolLayer(0) if symbol.symbolLayerCount() else None
    if marker is None:
        return
    for key, getter, setter in (("fill_opacity", "color", "setColor"), ("stroke_opacity", "strokeColor", "setStrokeColor")):
        if key not in params or not hasattr(marker, setter):
            continue
        colour = imports["QColor"](getattr(marker, getter)())
        colour.setAlphaF(_opacity_param(params, key, 1.0))
        getattr(marker, setter)(colour)


def _set_opacity(layer: Any, opacity: float) -> None:
    try:
        layer.setOpacity(max(0.0, min(1.0, float(opacity))))
    except Exception:
        pass


def apply_single_symbol(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    fill = str(params.get("fill_color", "#D8E1E8"))
    stroke = str(params.get("stroke_color", "#075D68"))
    stroke_width = float(params.get("stroke_width", 0.4))
    opacity = _opacity_param(params, "opacity", 1.0)
    fill_opacity = _opacity_param(params, "fill_opacity", opacity)
    stroke_opacity = _opacity_param(params, "stroke_opacity", 1.0)
    fill_style = str(params.get("fill_style", "solid")).strip().lower()
    outline_only = bool(params.get("outline_only", False)) or fill_style in {"no", "none", "transparent", "outline_only"}
    # Diâmetro do ponto, em mm: sem ele o assistente não tinha como seguir o
    # conselho de CART076 ("pontos menores e semitransparentes").
    size = params.get("size_mm")
    if size is not None:
        size = float(size)
        if not 0.1 <= size <= 30:
            raise ValidationError("BAD_REQUEST", "size_mm vai de 0,1 a 30.", {"size_mm": size})
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "layer_id": layer.id(),
            "style_type": "single_symbol",
            "size_mm": size,
            "fill_color": fill,
            "stroke_color": stroke,
            "fill_opacity": fill_opacity,
            "stroke_opacity": stroke_opacity,
            "outline_only": outline_only,
        }
    imports = _imports()
    symbol = _symbol_for_layer(layer, fill, stroke, stroke_width, fill_opacity, stroke_opacity, outline_only, size)
    if layer.geometryType() != _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Polygon"):
        # Em ponto e linha, a opacidade vai para o símbolo, e não para a camada:
        # uma camada semitransparente pode levar o QGIS a rasterizar o mapa no
        # PDF; e fill_opacity, que o marcador ignorava, vale para o preenchimento.
        symbol.setOpacity(opacity)
        if layer.geometryType() == _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Point"):
            _set_marker_alphas(symbol, params, imports)
        elif "stroke_opacity" in params:
            symbol.setColor(_qcolor(stroke, stroke_opacity))
    layer.setRenderer(imports["QgsSingleSymbolRenderer"](symbol))
    mark_style_origin(layer, STYLE_ORIGIN_USER)
    _set_opacity(layer, 1.0)
    layer.triggerRepaint()
    return {
        "layer_id": layer.id(),
        "layer_name": layer.name(),
        "style_type": "single_symbol",
        "fill_color": fill,
        "stroke_color": stroke,
        "stroke_width": stroke_width,
        "size_mm": size,
        "opacity": opacity,
        "fill_opacity": fill_opacity,
        "stroke_opacity": stroke_opacity,
        "outline_only": outline_only,
    }


#: Rótulos da categoria sem valor e da que reúne o que passou do limite.
_CATEGORY_TEXT = {
    "pt-BR": ("Sem informação", "Outros"), "en": ("No data", "Other"), "es": ("Sin información", "Otros"),
    "fr": ("Sans information", "Autres"), "de": ("Keine Angabe", "Sonstige"), "it": ("Nessun dato", "Altri"),
}


def _sort_key(value: Any) -> tuple[int, Any]:
    """Números em ordem numérica, textos em ordem alfabética, vazio por último."""
    if value is None or str(value) in ("", "NULL"):
        return (2, "")
    try:
        return (0, float(value))
    except (TypeError, ValueError):
        return (1, str(value).casefold())


def categorized_colours(count: int, palette: list[str] | None = None, ramp_key: str = "",
                        values: list[Any] | None = None) -> list[str]:
    """Uma cor por categoria, sem repetir: a paleta pedida, cores com significado, as qualitativas ou uma rampa.

    Sem paleta pedida, uma classe cujo nome diz o que ela é recebe a cor que
    o leitor espera — água azul, floresta verde, área urbana vermelha; na
    ordem alfabética, "Corpo d'água" saía laranja e "Vegetação campestre"
    azul. As demais recebem as qualitativas que sobraram.
    """
    from .raster_style import QUALITATIVE, semantic_colour

    if palette:
        if len(palette) < count:
            raise ValidationError("BAD_REQUEST", f"palette tem {len(palette)} cores para {count} categorias: as cores "
                                  "se repetiriam e classes diferentes ficariam iguais no mapa.",
                                  {"palette": len(palette), "categories": count})
        return [str(colour) for colour in palette[:count]]
    if ramp_key or count > len(QUALITATIVE):
        from .raster_style import qgis_ramp

        ramp = qgis_ramp(ramp_key or "Spectral")
        return [ramp.color(k / float(max(1, count - 1))).name() for k in range(count)]
    chosen: list[str | None] = [None] * count
    used: set[str] = set()
    for index, value in enumerate((values or [])[:count]):
        colour = semantic_colour(value)
        if colour and colour not in used:
            chosen[index] = colour
            used.add(colour)
    spare = [colour for colour in QUALITATIVE if colour not in used]
    return [colour if colour else spare.pop(0) for colour in chosen]


def _class_symbol(layer: Any, colour: str) -> Any:
    """Símbolo de uma classe: a cor vai no preenchimento do polígono, no traço da linha e no ponto.

    Num categorizado de linhas a cor da classe ia para um preenchimento que a
    linha não tem, e todas as classes saíam no mesmo cinza-escuro do traço.
    Polígonos miúdos e numerosos (células de uso da terra, unidades de solo)
    ganham borda fina: a borda de 0,35 mm desenhava a grade em vez do mapa.
    """
    imports = _imports()
    kind = layer.geometryType()
    try:
        count = int(layer.featureCount())
    except Exception:
        count = 0
    if kind == _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Line"):
        return _symbol_for_layer(layer, colour, colour, 0.3 if count > 300 else 0.45)
    if kind == _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Point"):
        return _symbol_for_layer(layer, colour, "#1E2A32", 0.25)
    return _symbol_for_layer(layer, colour, "#4D4D4D" if count > 200 else "#1E2A32", 0.1 if count > 200 else 0.26)


def _count_key(value: Any) -> str:
    return str(value)


def _value_counts(layer: Any, field_name: str) -> dict[str, int]:
    """Quantas feições têm cada valor do campo (chave: o valor como texto)."""
    from qgis.core import QgsFeatureRequest  # type: ignore

    request = QgsFeatureRequest()
    request.setSubsetOfAttributes([field_name], layer.fields())
    counts: dict[str, int] = {}
    for feature in layer.getFeatures(request):
        key = _count_key(feature[field_name])
        counts[key] = counts.get(key, 0) + 1
    return counts


def apply_categorized_style(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    field_name = require_param(params, "field_name", str)
    if not _field_exists(layer, field_name):
        raise ValidationError("FIELD_NOT_FOUND", "Field not found.", {"field_name": field_name})
    limit = max(1, int(params.get("limit", 40)))
    every = sorted(layer.uniqueValues(layer.fields().indexOf(field_name)), key=_sort_key)
    null_values = [value for value in every if value is None or str(value) in ("", "NULL")]
    values = [value for value in every if value not in null_values]
    overflow: list[Any] = []
    overflow_features = 0
    if len(values) > limit:
        # Ficam as classes com mais feições, não as primeiras da ordem
        # alfabética: com 120 classes e limit 12, "Outros" levava as de Z, por
        # maiores que fossem.
        counts = _value_counts(layer, field_name)
        ranked = sorted(values, key=lambda value: (-counts.get(_count_key(value), 0), _sort_key(value)))
        kept = set(map(_count_key, ranked[:limit]))
        overflow = [value for value in values if _count_key(value) not in kept]
        overflow_features = sum(counts.get(_count_key(value), 0) for value in overflow)
        values = [value for value in values if _count_key(value) in kept]
    from ..cartography.maptext import resolve_language
    from .raster_style import ramp_name

    language, _known = resolve_language(str(params.get("map_language") or "pt-BR"))
    no_data_text, other_text = _CATEGORY_TEXT.get(language, _CATEGORY_TEXT["en"])
    names = {str(k): str(v) for k, v in (params.get("labels") or {}).items()} if isinstance(params.get("labels"), dict) else {}
    warnings = []
    if overflow:
        warnings.append(f"Os {len(overflow)} valor(es) menos frequentes ({overflow_features} feição(ões)) passaram do "
                        f"limite de {limit} classes e foram reunidos na categoria '{other_text}'; ficaram as {limit} "
                        "classes com mais feições. Aumente limit ou agrupe as classes num campo próprio.")
    colours = categorized_colours(len(values), params.get("palette"), ramp_name(params.get("color_ramp") or ""), values)
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "field_name": field_name, "category_count": len(values),
                "values": [str(v) for v in values], "warnings": warnings}
    imports = _imports()
    categories = []
    for index, value in enumerate(values):
        symbol = _class_symbol(layer, colours[index])
        categories.append(imports["QgsRendererCategory"](value, symbol, names.get(str(value), str(value))))
    if null_values or overflow:
        # Categoria de valor vazio: no QGIS ela recebe tudo que nenhuma outra
        # recebeu — os sem valor E os que passaram do limite. As duas coisas
        # não se separam por categoria (uma categoria NULL faz o mesmo papel).
        text = (f"{other_text} / {no_data_text[0].lower()}{no_data_text[1:]}" if null_values and overflow
                else other_text if overflow else names.get("NULL", no_data_text))
        # Cinza que nenhuma das cores qualitativas confunde (o #D9D9D9 de
        # antes ficava a ΔE 13,6 do verde-claro sob tritanomalia).
        symbol = _class_symbol(layer, "#BDBDBD")
        categories.append(imports["QgsRendererCategory"]("", symbol, text))
    layer.setRenderer(imports["QgsCategorizedSymbolRenderer"](field_name, categories))
    mark_style_origin(layer, STYLE_ORIGIN_USER)
    _set_opacity(layer, float(params.get("opacity", 0.85)))
    layer.triggerRepaint()
    result = {"layer_id": layer.id(), "field_name": field_name, "style_type": "categorized", "category_count": len(categories)}
    if warnings:
        result["warnings"] = warnings
    return result


def apply_graduated_style(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    field_name = require_param(params, "field_name", str)
    if not _field_exists(layer, field_name):
        raise ValidationError("FIELD_NOT_FOUND", "Field not found.", {"field_name": field_name})
    values = []
    for feature in layer.getFeatures():
        try:
            value = float(feature[field_name])
            values.append(value)
        except Exception:
            continue
        if len(values) >= int(params.get("sample_limit", 10000)):
            break
    if not values:
        raise ValidationError("NO_NUMERIC_VALUES", "No numeric values found for graduated style.", {"field_name": field_name})
    classes = max(2, min(9, int(params.get("classes", 5))))
    method = str(params.get("method") or "equal_interval").strip().lower().replace("-", "_").replace(" ", "_")
    method = {"equal": "equal_interval", "quantiles": "quantile", "quantis": "quantile", "natural_breaks": "jenks",
              "intervalos_iguais": "equal_interval", "quebras_naturais": "jenks"}.get(method, method)
    if method not in GRADUATED_METHODS:
        raise ValidationError("BAD_REQUEST", f"method desconhecido: {method!r}. Aceitos: {', '.join(GRADUATED_METHODS)}.",
                              {"method": method})
    breaks = _class_breaks(sorted(values), classes, method)
    minimum, maximum = min(values), max(values)
    from ..cartography.maptext import resolve_language
    from .raster_style import class_labels, ramp_name

    language, _known = resolve_language(str(params.get("map_language") or "pt-BR"))
    labels = class_labels(breaks, str(params.get("unit") or "").strip(), language)
    ramp_key = ramp_name(params.get("color_ramp") or "")
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "field_name": field_name, "classes": len(breaks) - 1,
                "method": method, "breaks": breaks, "labels": labels, "min": minimum, "max": maximum}
    imports = _imports()
    ranges = []
    colors = _graduated_colours(len(breaks) - 1, ramp_key, bool(params.get("invert", False)))
    for index, (lower, upper) in enumerate(zip(breaks, breaks[1:])):
        symbol = _class_symbol(layer, colors[index])
        ranges.append(imports["QgsRendererRange"](lower, upper, symbol, labels[index]))
    layer.setRenderer(imports["QgsGraduatedSymbolRenderer"](field_name, ranges))
    mark_style_origin(layer, STYLE_ORIGIN_USER)
    _set_opacity(layer, float(params.get("opacity", 0.85)))
    layer.triggerRepaint()
    result = {"layer_id": layer.id(), "field_name": field_name, "style_type": "graduated", "classes": len(ranges),
              "method": method, "breaks": [round(value, 6) for value in breaks], "labels": labels}
    from ..cartography.vision import confusable_pairs

    warnings = []
    collapsed = collapsed_classes_warning(sorted(values), classes, len(ranges), method)
    if collapsed:
        warnings.append(collapsed)
    clashes = confusable_pairs([(labels[index], colour) for index, colour in enumerate(colors)])
    if clashes:
        # A auditoria acusaria depois (CART070); avisar aqui deixa o assistente
        # trocar a rampa ou o número de classes antes de compor.
        pares = "; ".join(f"{c['a']} × {c['b']}" for c in clashes[:3])
        warnings.append(f"Com esta rampa e {len(ranges)} classes há classes vizinhas que um leitor daltônico não "
                        f"distingue ({pares}). Use menos classes ou uma rampa de um matiz só (Blues, Greens, "
                        "Purples, Greys, Viridis).")
    if warnings:
        result["warnings"] = warnings
    return result


def collapsed_classes_warning(ordered: list[float], requested: int, obtained: int, method: str) -> str:
    """Aviso quando os limites de classe coincidem e saem menos classes que as pedidas.

    Contagens com muitos zeros — registros por município, por exemplo — fazem
    os quantis coincidirem: 5 classes pedidas, 1 entregue, e o mapa sai de uma
    cor só sem que nada dissesse por quê. Puro, para teste sem QGIS.
    """
    if obtained >= requested or not ordered:
        return ""
    mode = max(set(ordered), key=ordered.count)
    share = ordered.count(mode) / len(ordered)
    return (f"Pedidas {requested} classes por {method}, saíram {obtained}: {share:.0%} dos valores são {mode:g}, e os "
            "limites coincidem. Use method='jenks' ou 'pretty', ou classes explícitas, ou deixe o valor repetido "
            "numa classe só e classifique o resto.")


def _graduated_colours(count: int, ramp_key: str, invert: bool) -> list[str]:
    """Uma cor por classe, da rampa pedida (Greens por padrão), em passos iguais de claridade."""
    from .raster_style import lightness_positions, qgis_ramp

    ramp = qgis_ramp(ramp_key or "Greens", invert)
    samples = [ramp.color(k / 40.0).name() for k in range(41)]
    return [ramp.color(position).name() for position in lightness_positions(samples, count)]


_DENSITY_LABELS = {
    "pt-BR": ("Menor densidade", "Maior densidade"), "en": ("Lower density", "Higher density"),
    "es": ("Menor densidad", "Mayor densidad"), "fr": ("Densité faible", "Densité élevée"),
    "de": ("Geringe Dichte", "Hohe Dichte"), "it": ("Densità bassa", "Densità alta"),
}


def apply_heatmap_style(params: dict[str, Any], context: dict[str, Any]):
    """Mapa de calor (densidade de kernel desenhada pelo QGIS) para uma camada de pontos."""
    layer = _layer(require_param(params, "layer_id", str))
    imports = _imports()
    point = _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Point")
    if layer.geometryType() != point:
        raise ValidationError("POINT_LAYER_REQUIRED", "O mapa de calor precisa de uma camada de pontos.", {"layer_id": layer.id()})
    radius = float(params.get("radius", 6.0))
    if radius <= 0:
        raise ValidationError("BAD_REQUEST", "radius precisa ser maior que zero.", {"radius": radius})
    unit = str(params.get("radius_unit") or "mm").strip().lower()
    if unit not in ("mm", "map_units", "pixels"):
        raise ValidationError("BAD_REQUEST", "radius_unit aceita mm, map_units ou pixels.", {"radius_unit": unit})
    weight = params.get("weight_field")
    if weight and not _field_exists(layer, str(weight)):
        raise ValidationError("FIELD_NOT_FOUND", "Field not found.", {"field_name": weight})
    quality = max(1, min(5, int(params.get("quality", 3))))
    maximum = float(params.get("max_value", 0) or 0)
    from ..cartography.maptext import resolve_language
    from .raster_style import ramp_name

    language, _known = resolve_language(str(params.get("map_language") or "pt-BR"))
    ramp_key = ramp_name(params.get("color_ramp") or "heat")
    plan = {"layer_id": layer.id(), "style_type": "heatmap", "radius": radius, "radius_unit": unit,
            "weight_field": weight or None, "quality": quality, "max_value": maximum or "auto", "color_ramp": ramp_key}
    if context.get("dry_run"):
        return {"dry_run": True, **plan}
    from qgis.core import QgsColorRampLegendNodeSettings, QgsGradientColorRamp, QgsGradientStop, QgsHeatmapRenderer  # type: ignore

    from ..cartography.qtcompat import qt_enum
    from .raster_style import qgis_ramp

    source = qgis_ramp(ramp_key, bool(params.get("invert", False)))
    # A rampa começa transparente: densidade baixa deixa ver o que está por baixo.
    first = source.color(0.0)
    first.setAlpha(0)
    stops = [QgsGradientStop(position, source.color(position)) for position in (0.15, 0.35, 0.55, 0.75)]
    ramp = QgsGradientColorRamp(first, source.color(1.0), False, stops)
    renderer = QgsHeatmapRenderer()
    renderer.setRadius(radius)
    unit_member = {"mm": "Millimeters", "map_units": "MapUnits", "pixels": "Pixels"}[unit]
    try:
        renderer.setRadiusUnit(qt_enum(imports["Qgis"], "RenderUnit", unit_member))
    except Exception:
        pass
    renderer.setColorRamp(ramp)
    renderer.setRenderQuality(quality)
    renderer.setMaximumValue(maximum)
    if weight:
        renderer.setWeightExpression(f'"{weight}"')
    try:
        legend = QgsColorRampLegendNodeSettings()
        low, high = _DENSITY_LABELS.get(language, _DENSITY_LABELS["en"])
        legend.setMinimumLabel(low)
        legend.setMaximumLabel(high)
        renderer.setLegendSettings(legend)
    except Exception:
        pass
    layer.setRenderer(renderer)
    mark_style_origin(layer, STYLE_ORIGIN_USER)
    _set_opacity(layer, float(params.get("opacity", 1.0)))
    layer.triggerRepaint()
    return plan


def apply_proportional_symbol_style(params: dict[str, Any], context: dict[str, Any]):
    """Símbolo de ponto com área proporcional a um campo numérico, com legenda de tamanhos.

    Feito para os locais de count_points_by_site (um ponto por local, com o
    número de registros), mas serve a qualquer contagem ou medida por ponto.
    A área, e não o diâmetro, é proporcional ao valor; os maiores são
    desenhados primeiro, para que os pequenos fiquem à vista por cima. Para
    que os círculos não se amontoem, os locais de count_points_by_site devem
    ser agrupados na escala do mapa (parâmetro ``scale``); CART076 mede.
    """
    layer = _layer(require_param(params, "layer_id", str))
    imports = _imports()
    if layer.geometryType() != _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Point"):
        raise ValidationError("POINT_LAYER_REQUIRED", "O símbolo proporcional precisa de uma camada de pontos.", {"layer_id": layer.id()})
    field_name = require_param(params, "field_name", str)
    if not _field_exists(layer, field_name):
        raise ValidationError("FIELD_NOT_FOUND", "Field not found.", {"field_name": field_name})
    values = []
    for feature in layer.getFeatures():
        try:
            values.append(float(feature[field_name]))
        except Exception:
            continue
    values = [v for v in values if v == v and v >= 0]
    if not values:
        raise ValidationError("NO_NUMERIC_VALUES", "O campo não tem valores numéricos não negativos.", {"field_name": field_name})
    # min_value/max_value fixam a régua: dois painéis comparáveis (registros
    # antes e depois de 2015) precisam do mesmo tamanho para o mesmo número,
    # e cada camada, sozinha, iria do seu menor ao seu maior valor.
    try:
        minimum = float(params["min_value"]) if params.get("min_value") is not None else min(values)
        maximum = float(params["max_value"]) if params.get("max_value") is not None else max(values)
    except (TypeError, ValueError) as exc:
        raise ValidationError("BAD_REQUEST", "min_value e max_value precisam ser números.", {}) from exc
    if not 0 <= minimum <= maximum:
        raise ValidationError("BAD_REQUEST", "Use 0 <= min_value <= max_value.", {"min_value": minimum, "max_value": maximum})
    outside = sum(1 for v in values if v < minimum or v > maximum)
    min_size = float(params.get("min_size_mm", 1.0))
    max_size = float(params.get("max_size_mm", 8.0))
    if not 0 < min_size < max_size <= 30:
        raise ValidationError("BAD_REQUEST", "Use 0 < min_size_mm < max_size_mm <= 30.", {"min_size_mm": min_size, "max_size_mm": max_size})
    colour = str(params.get("color") or "#0072B2")
    opacity = _opacity_param(params, "opacity", 0.75)
    outline = str(params.get("outline_color") or shade(colour, PROPORTIONAL_OUTLINE_SHADE))
    outline_width = float(params.get("outline_width_mm", 0.2))
    classes = params.get("legend_classes") or size_legend_values(minimum, maximum, min_size, max_size)
    try:
        classes = sorted({float(c) for c in classes if minimum <= float(c) <= maximum})
    except Exception as exc:
        raise ValidationError("BAD_REQUEST", "legend_classes precisa ser uma lista de números.", {}) from exc
    # legend_title vazio é pedido de legenda sem título (o nome da camada já
    # diz o que os círculos contam); antes ele virava o nome do campo.
    title = str(params["legend_title"] or "").strip() if "legend_title" in params else field_name
    from ..cartography.maptext import resolve_language

    language, _known = resolve_language(str(params.get("map_language") or "pt-BR"))
    plan = {"layer_id": layer.id(), "style_type": "proportional_symbol", "field_name": field_name,
            "min": minimum, "max": maximum, "min_size_mm": min_size, "max_size_mm": max_size,
            "scaling": "area", "legend_classes": classes, "legend_title": title, "color": colour, "opacity": opacity}
    if outside:
        plan["warnings"] = [f"{outside} feição(ões) fora de min_value/max_value: saem no menor ou no maior símbolo."]
    if context.get("dry_run"):
        return {"dry_run": True, **plan}
    from qgis.core import (QgsDataDefinedSizeLegend, QgsFeatureRequest, QgsProperty,  # type: ignore
                           QgsSizeScaleTransformer)

    symbol = imports["QgsMarkerSymbol"].createSimple({
        "name": "circle", "color": colour, "outline_color": outline,
        "outline_width": str(outline_width), "size": str(min_size)})
    symbol.setOpacity(opacity)
    scale_type = getattr(getattr(QgsSizeScaleTransformer, "ScaleType", QgsSizeScaleTransformer), "Area")
    transformer = QgsSizeScaleTransformer(scale_type, minimum, maximum if maximum > minimum else minimum + 1.0,
                                          min_size, max_size, 0.0, 0.5)
    size = QgsProperty.fromField(field_name)
    size.setTransformer(transformer)
    symbol.setDataDefinedSize(size)
    renderer = imports["QgsSingleSymbolRenderer"](symbol)
    renderer.setOrderBy(QgsFeatureRequest.OrderBy([QgsFeatureRequest.OrderByClause(field_name, False)]))
    renderer.setOrderByEnabled(True)

    def label(value: float) -> str:
        text = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"
        return text.replace(",", ".") if language.startswith("pt") or language in ("es", "de", "it") else text

    legend = QgsDataDefinedSizeLegend()
    legend.setLegendType(getattr(getattr(QgsDataDefinedSizeLegend, "LegendType", QgsDataDefinedSizeLegend), "LegendCollapsed"))
    legend.setClasses([QgsDataDefinedSizeLegend.SizeClass(value, label(value)) for value in classes])
    legend.setTitle(title)
    renderer.setDataDefinedSizeLegend(legend)
    layer.setRenderer(renderer)
    mark_style_origin(layer, STYLE_ORIGIN_USER)
    layer.triggerRepaint()
    return plan


#: Métodos de classificação de apply_graduated_style.
GRADUATED_METHODS = ("equal_interval", "quantile", "jenks", "pretty")


def _class_breaks(values: list[float], classes: int, method: str) -> list[float]:
    """Limites de classe (classes + 1 valores, do mínimo ao máximo) para valores já ordenados.

    Puro, para ser testado sem QGIS. Quantis repartem as feições em partes
    iguais; Jenks minimiza a variância dentro das classes (Jenks, 1967);
    "pretty" arredonda para números redondos. Limites repetidos (muitos
    valores iguais) são fundidos — melhor menos classes que classe vazia.
    """
    low, high = values[0], values[-1]
    if high <= low:
        return [low, high if high > low else low + 1.0]
    if method == "quantile":
        n = len(values)
        cuts = [values[min(n - 1, int(round(n * k / classes)))] for k in range(1, classes)]
    elif method == "jenks":
        cuts = _jenks_cuts(values, classes)
    elif method == "pretty":
        from ..cartography.scaling import nice_number

        step = nice_number((high - low) / classes, "nearest")
        start = (low // step) * step
        cuts = [start + step * k for k in range(1, classes + 3) if low < start + step * k < high]
    else:
        step = (high - low) / classes
        cuts = [low + step * k for k in range(1, classes)]
    edges = [low] + [c for c in cuts if low < c < high] + [high]
    merged = [edges[0]]
    for edge in edges[1:]:
        if edge > merged[-1]:
            merged.append(edge)
    return merged


def _jenks_cuts(values: list[float], classes: int, sample: int = 1000) -> list[float]:
    """Quebras naturais de Jenks por programação dinâmica (amostra de até ``sample`` valores)."""
    if len(values) > sample:
        step = len(values) / float(sample)
        values = [values[int(i * step)] for i in range(sample)] + [values[-1]]
    n = len(values)
    classes = min(classes, n)
    lower = [[0] * (classes + 1) for _ in range(n + 1)]
    variance = [[float("inf")] * (classes + 1) for _ in range(n + 1)]
    for j in range(1, classes + 1):
        lower[1][j] = 1
        variance[1][j] = 0.0
    for i in range(2, n + 1):
        total = total_sq = weight = 0.0
        for m in range(1, i + 1):
            value = values[i - m]
            total += value
            total_sq += value * value
            weight += 1
            cost = total_sq - total * total / weight
            k = i - m
            if k:
                for j in range(2, classes + 1):
                    if variance[i][j] >= cost + variance[k][j - 1]:
                        lower[i][j] = k + 1
                        variance[i][j] = cost + variance[k][j - 1]
        lower[i][1] = 1
        variance[i][1] = cost
    cuts = []
    k = n
    for j in range(classes, 1, -1):
        index = lower[k][j] - 2
        cuts.append(values[max(0, index)])
        k = lower[k][j] - 1
    return sorted(cuts)


def set_layer_opacity(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    opacity = float(params.get("opacity", 1.0))
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "opacity": opacity}
    _set_opacity(layer, opacity)
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "opacity": opacity}


def _hex_colour(value: Any) -> Any:
    """'127,59,8,255' (formato das propriedades de símbolo do QGIS) → '#7f3b08'."""
    text = str(value)
    parts = text.split(",")
    if len(parts) in (3, 4) and all(part.strip().isdigit() for part in parts):
        r, g, b = (int(part) for part in parts[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    return value


def _symbol_summary(symbol: Any) -> dict[str, Any]:
    """Cor, contorno, largura e preenchimento de um símbolo, como texto."""
    summary: dict[str, Any] = {}
    try:
        summary["color"] = symbol.color().name()
        summary["opacity"] = round(float(symbol.opacity()), 3)
    except Exception:
        pass
    try:
        first = symbol.symbolLayer(0)
        props = dict(first.properties())
        for source, target in (("outline_color", "stroke_color"), ("outline_width", "stroke_width"), ("outline_style", "stroke_style"),
                               ("style", "fill_style"), ("line_width", "stroke_width"), ("size", "size"), ("name", "marker")):
            if source in props and target not in summary:
                summary[target] = _hex_colour(props[source]) if target.endswith("color") else props[source]
        if "fill_style" in summary:
            summary["outline_only"] = str(summary["fill_style"]) == "no"
    except Exception:
        pass
    return summary


def inspect_layer_style(params: dict[str, Any], context: dict[str, Any]):
    """O estilo em vigor, com o símbolo por extenso.

    A versão anterior devolvia só o tipo do renderizador: quem aplicava uma
    cor por apply_single_symbol não tinha como confirmar o que ficou.
    """
    layer = _layer(require_param(params, "layer_id", str))
    renderer = layer.renderer()
    renderer_type = renderer.type() if renderer else ""
    result: dict[str, Any] = {
        "layer_id": layer.id(),
        "layer_name": layer.name(),
        "renderer_type": renderer_type,
        "style_origin": style_origin(layer) or "project",
        "opacity": layer.opacity() if hasattr(layer, "opacity") else None,
        "labels_enabled": bool(layer.labelsEnabled()),
    }
    try:
        if renderer_type == "singleSymbol":
            result["symbol"] = _symbol_summary(renderer.symbol())
        elif renderer_type == "categorizedSymbol":
            result["field"] = renderer.classAttribute()
            categories = list(renderer.categories())
            result["category_count"] = len(categories)
            result["categories"] = [
                {"value": str(category.value()), "label": category.label(), **_symbol_summary(category.symbol())}
                for category in categories[:25]
            ]
        elif renderer_type == "graduatedSymbol":
            result["field"] = renderer.classAttribute()
            ranges = list(renderer.ranges())
            result["class_count"] = len(ranges)
            result["classes"] = [
                {"lower": item.lowerValue(), "upper": item.upperValue(), "label": item.label(), **_symbol_summary(item.symbol())}
                for item in ranges[:25]
            ]
        elif renderer_type in ("embeddedSymbol", "RuleRenderer") and hasattr(renderer, "symbols"):
            result["note"] = "estilo por feição ou por regra; use apply_single_symbol ou apply_categorized_style para uma legenda por camada"
    except Exception as exc:
        result["symbol_error"] = str(exc)[:200]
    return result


def save_qml_style(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    path = normalize_output_path(require_param(params, "output_path", str))
    ensure_parent_exists(path)
    try:
        reject_existing_path_without_confirmation(path, bool(params.get("confirm_overwrite", False)))
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(path)}) from exc
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "output_path": str(path)}
    ok, message = _style_result(layer.saveNamedStyle(str(path)))
    return {"layer_id": layer.id(), "output_path": str(path), "saved": ok, "message": message}


def _style_result(result: Any) -> tuple[bool, str]:
    """(sucesso, mensagem) de loadNamedStyle/saveNamedStyle, que o PyQGIS devolve como (mensagem, sucesso).

    Lido na ordem inversa, o estilo carregado saía como não carregado e não era
    marcado como do usuário, e a composição podia trocá-lo pela paleta.
    """
    first, second = result
    if isinstance(first, bool):
        return first, str(second or "")
    return bool(second), str(first or "")


def load_qml_style(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    path = Path(require_param(params, "path", str))
    if not path.exists():
        raise ValidationError("FILE_NOT_FOUND", "QML style file not found.", {"path": str(path)})
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "path": str(path)}
    ok, message = _style_result(layer.loadNamedStyle(str(path)))
    if ok:
        mark_style_origin(layer, STYLE_ORIGIN_USER)
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "path": str(path), "loaded": ok, "message": message}


def recommend_style_for_layer(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    geometry = layer.geometryType()
    profile = "scientific_soft"
    if geometry == _geometry_type(_imports()["Qgis"], _imports()["QgsWkbTypes"], "Line"):
        profile = "technical_blue"
    elif geometry == _geometry_type(_imports()["Qgis"], _imports()["QgsWkbTypes"], "Point"):
        profile = "contrast_highlight"
    return {"layer_id": layer.id(), "layer_name": layer.name(), "recommended_profile": profile, "reason": "Based on vector geometry type and publication-safe defaults."}


def create_labels(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    field_name = require_param(params, "field_name", str)
    if not _field_exists(layer, field_name):
        raise ValidationError("FIELD_NOT_FOUND", "Field not found.", {"field_name": field_name})
    return _apply_labels(layer, field_name, params, context, is_expression=False)


def create_labels_from_expression(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    expression = require_param(params, "expression", str)
    return _apply_labels(layer, expression, params, context, is_expression=True)


def _apply_labels(layer: Any, value: str, params: dict[str, Any], context: dict[str, Any], is_expression: bool):
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "label": value, "is_expression": is_expression}
    imports = _imports()
    settings = imports["QgsPalLayerSettings"]()
    settings.fieldName = value
    settings.isExpression = bool(is_expression)
    text_format = imports["QgsTextFormat"]()
    font = imports["QFont"]()
    font.setPointSize(int(params.get("font_size", 8)))
    text_format.setFont(font)
    text_format.setSize(float(params.get("font_size", 8)))
    if bool(params.get("buffer", True)):
        buffer_settings = imports["QgsTextBufferSettings"]()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(float(params.get("buffer_size", 1.0)))
        buffer_settings.setColor(imports["QColor"](str(params.get("buffer_color", "#FFFFFF"))))
        text_format.setBuffer(buffer_settings)
    notes = []
    if layer.geometryType() == _geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Line"):
        notes = _line_label_settings(layer, settings, text_format, imports)
    settings.setFormat(text_format)
    layer.setLabeling(imports["QgsVectorLayerSimpleLabeling"](settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
    result = {"layer_id": layer.id(), "labels_enabled": True, "label": value, "is_expression": is_expression}
    if notes:
        result["notes"] = notes
    return result


#: Nome de camada que indica hidrografia: o rótulo vai em itálico azul, a
#: convenção das cartas para hidrônimos.
_HYDRO_TERMS = ("rio", "rios", "drenag", "hidro", "curso", "água", "agua", "stream", "river", "water", "riacho", "córrego")


def _line_label_settings(layer: Any, settings: Any, text_format: Any, imports: dict[str, Any]) -> list[str]:
    """Rótulo de linha que acompanha a linha, um por feição contínua.

    Com o posicionamento padrão (o de ponto) o rótulo de um rio não cabia em
    nenhum trecho curto da drenagem e o motor descartava todos — 187 nomes
    na bateria de mapas, nenhum no papel. Curvo, sobre a linha, e com os
    trechos conectados de mesmo nome fundidos: um nome por rio.
    """
    from ..cartography.qtcompat import qt_enum

    notes = []
    try:
        settings.placement = qt_enum(imports["Qgis"], "LabelPlacement", "Curved")
    except Exception:
        try:
            settings.placement = qt_enum(imports["QgsPalLayerSettings"], "Placement", "Curved")
        except Exception:
            pass
    try:
        settings.lineSettings().setMergeLines(True)
        notes.append("Trechos conectados de mesmo nome fundidos num rótulo só.")
    except Exception:
        pass
    # Trecho mais curto que isto (mm no papel) não comporta o próprio nome:
    # nem vira candidato, em vez de ser descartado pelo motor.
    try:
        settings.minFeatureSize = 12.0
    except Exception:
        pass
    name = str(layer.name()).casefold()
    if any(term in name for term in _HYDRO_TERMS):
        font = text_format.font()
        font.setItalic(True)
        text_format.setFont(font)
        text_format.setColor(imports["QColor"]("#1F5F8B"))
        notes.append("Hidronímia em itálico azul, como nas cartas.")
    return notes


def enable_labels(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "labels_enabled": True}
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "labels_enabled": True}


def disable_labels(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "labels_enabled": False}
    layer.setLabelsEnabled(False)
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "labels_enabled": False}
