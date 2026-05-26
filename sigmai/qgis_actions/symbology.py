from __future__ import annotations

from pathlib import Path
from typing import Any

from ..security import ensure_parent_exists, normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param
from .common import layer_type_name, project


def _imports() -> dict[str, Any]:
    try:
        from qgis.PyQt.QtCore import Qt  # type: ignore
        from qgis.PyQt.QtGui import QColor, QFont  # type: ignore
        from qgis.core import (  # type: ignore
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
):
    imports = _imports()
    geometry_type = layer.geometryType()
    if geometry_type == imports["QgsWkbTypes"].PointGeometry:
        return imports["QgsMarkerSymbol"].createSimple({"color": fill, "outline_color": stroke, "outline_width": str(stroke_width)})
    if geometry_type == imports["QgsWkbTypes"].LineGeometry:
        return imports["QgsLineSymbol"].createSimple({"color": stroke, "line_width": str(stroke_width)})
    style = "no" if outline_only else "solid"
    symbol = imports["QgsFillSymbol"].createSimple({"color": fill, "style": style, "outline_color": stroke, "outline_width": str(stroke_width)})
    _apply_fill_symbol_details(symbol, fill, stroke, fill_opacity, stroke_opacity, stroke_width, outline_only)
    return symbol


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
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "layer_id": layer.id(),
            "style_type": "single_symbol",
            "fill_color": fill,
            "stroke_color": stroke,
            "fill_opacity": fill_opacity,
            "stroke_opacity": stroke_opacity,
            "outline_only": outline_only,
        }
    imports = _imports()
    symbol = _symbol_for_layer(layer, fill, stroke, stroke_width, fill_opacity, stroke_opacity, outline_only)
    layer.setRenderer(imports["QgsSingleSymbolRenderer"](symbol))
    _set_opacity(layer, opacity if layer.geometryType() != imports["QgsWkbTypes"].PolygonGeometry else 1.0)
    layer.triggerRepaint()
    return {
        "layer_id": layer.id(),
        "layer_name": layer.name(),
        "style_type": "single_symbol",
        "opacity": opacity,
        "fill_opacity": fill_opacity,
        "stroke_opacity": stroke_opacity,
        "outline_only": outline_only,
    }


def apply_categorized_style(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    field_name = require_param(params, "field_name", str)
    if not _field_exists(layer, field_name):
        raise ValidationError("FIELD_NOT_FOUND", "Field not found.", {"field_name": field_name})
    values = layer.uniqueValues(layer.fields().indexOf(field_name), int(params.get("limit", 20)))
    palette = params.get("palette") or ["#00A86B", "#075D68", "#F5A623", "#D94A4A", "#6B7A86", "#20E39A"]
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "field_name": field_name, "category_count": len(values)}
    imports = _imports()
    categories = []
    for index, value in enumerate(values):
        color = str(palette[index % len(palette)])
        symbol = _symbol_for_layer(layer, color, "#1E2A32", 0.35)
        categories.append(imports["QgsRendererCategory"](value, symbol, str(value)))
    layer.setRenderer(imports["QgsCategorizedSymbolRenderer"](field_name, categories))
    _set_opacity(layer, float(params.get("opacity", 0.85)))
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "field_name": field_name, "style_type": "categorized", "category_count": len(categories)}


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
    minimum, maximum = min(values), max(values)
    step = (maximum - minimum) / classes if maximum > minimum else 1
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "field_name": field_name, "classes": classes, "min": minimum, "max": maximum}
    imports = _imports()
    ranges = []
    colors = ["#E8F5E9", "#C8E6C9", "#81C784", "#43A047", "#1B5E20", "#075D68", "#003B5C", "#062A3A", "#041B26"]
    for index in range(classes):
        lower = minimum + step * index
        upper = maximum if index == classes - 1 else minimum + step * (index + 1)
        symbol = _symbol_for_layer(layer, colors[index % len(colors)], "#1E2A32", 0.25)
        ranges.append(imports["QgsRendererRange"](lower, upper, symbol, f"{lower:.2f} - {upper:.2f}"))
    layer.setRenderer(imports["QgsGraduatedSymbolRenderer"](field_name, ranges))
    _set_opacity(layer, float(params.get("opacity", 0.85)))
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "field_name": field_name, "style_type": "graduated", "classes": classes}


def set_layer_opacity(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    opacity = float(params.get("opacity", 1.0))
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "opacity": opacity}
    _set_opacity(layer, opacity)
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "opacity": opacity}


def inspect_layer_style(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    renderer = layer.renderer()
    return {"layer_id": layer.id(), "layer_name": layer.name(), "renderer_type": renderer.type() if renderer else "", "opacity": layer.opacity() if hasattr(layer, "opacity") else None, "labels_enabled": bool(layer.labelsEnabled())}


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
    ok, message = layer.saveNamedStyle(str(path))
    return {"layer_id": layer.id(), "output_path": str(path), "saved": bool(ok), "message": message}


def load_qml_style(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    path = Path(require_param(params, "path", str))
    if not path.exists():
        raise ValidationError("FILE_NOT_FOUND", "QML style file not found.", {"path": str(path)})
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "path": str(path)}
    ok, message = layer.loadNamedStyle(str(path))
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "path": str(path), "loaded": bool(ok), "message": message}


def recommend_style_for_layer(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    geometry = layer.geometryType()
    profile = "scientific_soft"
    if geometry == _imports()["QgsWkbTypes"].LineGeometry:
        profile = "technical_blue"
    elif geometry == _imports()["QgsWkbTypes"].PointGeometry:
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
    settings.setFormat(text_format)
    layer.setLabeling(imports["QgsVectorLayerSimpleLabeling"](settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
    return {"layer_id": layer.id(), "labels_enabled": True, "label": value, "is_expression": is_expression}


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
