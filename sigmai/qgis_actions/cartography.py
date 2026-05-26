from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..security import ensure_parent_exists, normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param
from .common import crs_authid, extent_to_dict, layer_type_name, project
from .export_layout import handle as export_layout
from .user_profile import read_user_profile


LAYOUT_TEMPLATES: dict[str, dict[str, Any]] = {
    "scientific_basic": {
        "description": "Clean A4 technical map with filtered legend, scale, north arrow, source and SIGMAI/QGIS software credit.",
        "map": {"x": 12, "y": 30, "width": 176, "height": 135},
        "legend": {"x": 198, "y": 32, "width": 78, "height": 74},
        "north": {"x": 188, "y": 32, "width": 10, "height": 18},
        "scale": {"x": 16, "y": 170, "width": 62, "height": 8},
        "title": {"x": 12, "y": 8, "width": 264, "height": 10, "font_size": 16},
        "subtitle": {"x": 12, "y": 19, "width": 264, "height": 7, "font_size": 9},
        "source": {"x": 12, "y": 190, "width": 264, "height": 7, "font_size": 7},
        "logo": {"x": 242, "y": 180, "width": 30, "height": 12},
    },
    "scientific_publication": {
        "description": "Publication-oriented map with larger map body, compact legend and restrained technical typography.",
        "map": {"x": 10, "y": 28, "width": 184, "height": 142},
        "legend": {"x": 202, "y": 30, "width": 72, "height": 82},
        "north": {"x": 182, "y": 32, "width": 10, "height": 18},
        "scale": {"x": 14, "y": 174, "width": 68, "height": 8},
        "title": {"x": 10, "y": 7, "width": 264, "height": 10, "font_size": 17},
        "subtitle": {"x": 10, "y": 18, "width": 264, "height": 7, "font_size": 9},
        "source": {"x": 10, "y": 190, "width": 230, "height": 7, "font_size": 7},
        "logo": {"x": 242, "y": 179, "width": 32, "height": 13},
    },
    "environmental_report": {
        "description": "Environmental planning report layout with green accents and generous source/authorship area.",
        "map": {"x": 12, "y": 31, "width": 174, "height": 134},
        "legend": {"x": 198, "y": 34, "width": 78, "height": 84},
        "north": {"x": 188, "y": 34, "width": 10, "height": 18},
        "scale": {"x": 16, "y": 171, "width": 65, "height": 8},
        "title": {"x": 12, "y": 8, "width": 264, "height": 10, "font_size": 16},
        "subtitle": {"x": 12, "y": 19, "width": 264, "height": 7, "font_size": 9},
        "source": {"x": 12, "y": 188, "width": 264, "height": 9, "font_size": 7},
        "logo": {"x": 242, "y": 177, "width": 32, "height": 13},
    },
    "minimal_clean": {
        "description": "Minimal map with wide map body and small supporting elements.",
        "map": {"x": 10, "y": 25, "width": 190, "height": 148},
        "legend": {"x": 207, "y": 28, "width": 68, "height": 72},
        "north": {"x": 190, "y": 29, "width": 9, "height": 16},
        "scale": {"x": 14, "y": 176, "width": 58, "height": 8},
        "title": {"x": 10, "y": 8, "width": 264, "height": 10, "font_size": 15},
        "subtitle": {"x": 10, "y": 18, "width": 264, "height": 6, "font_size": 8},
        "source": {"x": 10, "y": 191, "width": 264, "height": 6, "font_size": 7},
        "logo": {"x": 246, "y": 180, "width": 28, "height": 11},
    },
    "technical_dark": {
        "description": "Dark technical template placeholder using the same safe layout geometry; dark full styling is planned.",
        "map": {"x": 12, "y": 30, "width": 176, "height": 135},
        "legend": {"x": 198, "y": 32, "width": 78, "height": 74},
        "north": {"x": 188, "y": 32, "width": 10, "height": 18},
        "scale": {"x": 16, "y": 170, "width": 62, "height": 8},
        "title": {"x": 12, "y": 8, "width": 264, "height": 10, "font_size": 16},
        "subtitle": {"x": 12, "y": 19, "width": 264, "height": 7, "font_size": 9},
        "source": {"x": 12, "y": 190, "width": 264, "height": 7, "font_size": 7},
        "logo": {"x": 242, "y": 180, "width": 30, "height": 12},
    },
    "atlas_page": {
        "description": "Single-page atlas-style template; formal atlas export is a later phase.",
        "map": {"x": 12, "y": 30, "width": 176, "height": 135},
        "legend": {"x": 198, "y": 32, "width": 78, "height": 74},
        "north": {"x": 188, "y": 32, "width": 10, "height": 18},
        "scale": {"x": 16, "y": 170, "width": 62, "height": 8},
        "title": {"x": 12, "y": 8, "width": 264, "height": 10, "font_size": 16},
        "subtitle": {"x": 12, "y": 19, "width": 264, "height": 7, "font_size": 9},
        "source": {"x": 12, "y": 190, "width": 264, "height": 7, "font_size": 7},
        "logo": {"x": 242, "y": 180, "width": 30, "height": 12},
    },
}


STYLE_PROFILES: dict[str, dict[str, str | float]] = {
    "scientific_soft": {"fill_color": "#D8E1E8", "stroke_color": "#075D68", "stroke_width": 0.35, "opacity": 0.82},
    "environmental_green": {"fill_color": "#BFE7D4", "stroke_color": "#006B4A", "stroke_width": 0.38, "opacity": 0.78},
    "technical_blue": {"fill_color": "#CFE3EF", "stroke_color": "#003B5C", "stroke_width": 0.42, "opacity": 0.82},
    "monochrome_publication": {"fill_color": "#E6E6E6", "stroke_color": "#222222", "stroke_width": 0.32, "opacity": 0.88},
    "contrast_highlight": {"fill_color": "#F5A623", "stroke_color": "#062A3A", "stroke_width": 0.55, "opacity": 0.72},
    "terrain_context": {"fill_color": "#D9E3C3", "stroke_color": "#6F7F45", "stroke_width": 0.35, "opacity": 0.80},
    "biodiversity_report": {"fill_color": "#CDEAD7", "stroke_color": "#00A86B", "stroke_width": 0.45, "opacity": 0.76},
    "protected_area_map": {"fill_color": "#D8F3DC", "stroke_color": "#1B5E20", "stroke_width": 0.50, "opacity": 0.72},
}


def _imports() -> dict[str, Any]:
    try:
        from qgis.PyQt.QtCore import Qt  # type: ignore
        from qgis.PyQt.QtGui import QColor, QFont, QImage  # type: ignore
        from qgis.core import (  # type: ignore
            QgsFillSymbol,
            QgsLayoutItemLabel,
            QgsLayoutItemLegend,
            QgsLayoutItemMap,
            QgsLayoutItemPicture,
            QgsLayoutItemScaleBar,
            QgsLayoutPoint,
            QgsLayoutSize,
            QgsLineSymbol,
            QgsMarkerSymbol,
            QgsPrintLayout,
            QgsProject,
            QgsRectangle,
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsSingleSymbolRenderer,
            QgsUnitTypes,
            QgsWkbTypes,
        )
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc
    return locals()


def _layout(layout_name: str):
    layout = project().layoutManager().layoutByName(layout_name)
    if layout is None:
        raise ValidationError("LAYOUT_NOT_FOUND", "Layout not found.", {"layout_name": layout_name})
    return layout


def _layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_LAYER", "Layer is invalid.", {"layer_id": layer_id})
    return layer


def _ensure_layer_visible(layer_id: str) -> bool:
    try:
        node = project().layerTreeRoot().findLayer(layer_id)
        if node is not None:
            node.setItemVisibilityChecked(True)
            return True
    except Exception:
        pass
    return False


def _is_vector_layer_id(layer_id: str) -> bool:
    return layer_type_name(_layer(layer_id)) == "vector"


def _map_item(layout: Any, item_id: str):
    item = layout.itemById(item_id)
    if item is None:
        raise ValidationError("LAYOUT_ITEM_NOT_FOUND", "Layout item was not found.", {"item_id": item_id})
    if not hasattr(item, "setExtent"):
        raise ValidationError("MAP_ITEM_REQUIRED", "Layout item is not a map item.", {"item_id": item_id})
    return item


def _position_item(item: Any, x: float, y: float, width: float, height: float) -> None:
    imports = _imports()
    unit = imports["QgsUnitTypes"].LayoutMillimeters
    item.attemptMove(imports["QgsLayoutPoint"](float(x), float(y), unit))
    item.attemptResize(imports["QgsLayoutSize"](float(width), float(height), unit))


def _rect_to_dict(rect: Any) -> dict[str, float]:
    return {
        "xmin": float(rect.xMinimum()),
        "ymin": float(rect.yMinimum()),
        "xmax": float(rect.xMaximum()),
        "ymax": float(rect.yMaximum()),
    }


def _extent_from_params(params: dict[str, Any]):
    imports = _imports()
    if "extent" in params:
        extent = params["extent"]
        if not isinstance(extent, dict):
            raise ValidationError("BAD_REQUEST", "extent must be an object.", {"extent": extent})
        try:
            xmin = float(extent["xmin"])
            ymin = float(extent["ymin"])
            xmax = float(extent["xmax"])
            ymax = float(extent["ymax"])
        except Exception as exc:
            raise ValidationError("BAD_REQUEST", "extent must include numeric xmin, ymin, xmax, ymax.", {"extent": extent}) from exc
        if xmin >= xmax or ymin >= ymax:
            raise ValidationError("BAD_REQUEST", "Invalid extent bounds.", {"extent": extent})
        return imports["QgsRectangle"](xmin, ymin, xmax, ymax)
    layer_id = require_param(params, "layer_id", str)
    layer = _layer(layer_id)
    rect = _layer_extent_in_project_crs(layer)
    if rect is None or rect.isNull() or rect.isEmpty():
        raise ValidationError("INVALID_EXTENT", "Layer extent is invalid.", {"layer_id": layer_id})
    return rect


def _layer_extent_in_project_crs(layer: Any):
    rect = layer.extent()
    try:
        source_crs = layer.crs()
        dest_crs = project().crs()
        if source_crs.isValid() and dest_crs.isValid() and source_crs.authid() != dest_crs.authid():
            transform = _imports()["QgsCoordinateTransform"](source_crs, dest_crs, project())
            rect = transform.transformBoundingBox(rect)
    except Exception:
        pass
    return rect


def _target_map_crs(params: dict[str, Any]):
    map_crs = str(params.get("map_crs", "")).strip()
    if not map_crs:
        return None
    crs = _imports()["QgsCoordinateReferenceSystem"](map_crs)
    if not crs.isValid():
        raise ValidationError("INVALID_CRS", "map_crs is invalid.", {"map_crs": map_crs})
    return crs


def _layer_extent_in_target_crs(layer: Any, target_crs: Any | None):
    if target_crs is None:
        return _layer_extent_in_project_crs(layer)
    rect = layer.extent()
    try:
        source_crs = layer.crs()
        if source_crs.isValid() and target_crs.isValid() and source_crs.authid() != target_crs.authid():
            transform = _imports()["QgsCoordinateTransform"](source_crs, target_crs, project())
            rect = transform.transformBoundingBox(rect)
    except Exception:
        pass
    return rect


def _with_margin(rect: Any, margin_percent: float):
    imports = _imports()
    margin = max(0.0, float(margin_percent)) / 100.0
    width = rect.width()
    height = rect.height()
    dx = width * margin
    dy = height * margin
    return imports["QgsRectangle"](
        rect.xMinimum() - dx,
        rect.yMinimum() - dy,
        rect.xMaximum() + dx,
        rect.yMaximum() + dy,
    )


def _warnings_for_layer(layer: Any) -> list[str]:
    warnings: list[str] = []
    try:
        crs = layer.crs()
        if crs.isValid() and crs.isGeographic():
            warnings.append("Layer CRS is geographic. It is acceptable for location maps, but metric scale/analysis may need a projected CRS.")
    except Exception:
        pass
    return warnings


def add_layout_map(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    layer_id = require_param(params, "layer_id", str)
    raw_layer_ids = params.get("layer_ids", params.get("map_layer_ids", [layer_id]))
    if isinstance(raw_layer_ids, str):
        map_layer_ids = [raw_layer_ids]
    elif isinstance(raw_layer_ids, list):
        map_layer_ids = [str(value) for value in raw_layer_ids if str(value)]
    else:
        raise ValidationError("BAD_REQUEST", "layer_ids/map_layer_ids must be a string or list of strings.", {"value": raw_layer_ids})
    if layer_id not in map_layer_ids:
        map_layer_ids.append(layer_id)
    item_id = params.get("item_id", "main_map")
    x = float(params.get("x", 10))
    y = float(params.get("y", 25))
    width = float(params.get("width", 190))
    height = float(params.get("height", 150))
    margin_percent = float(params.get("margin_percent", 5))
    layer = _layer(layer_id)
    map_layers = [_layer(candidate_id) for candidate_id in map_layer_ids]
    target_crs = _target_map_crs(params)
    layer_visibility_changed = _ensure_layer_visible(layer_id)
    for candidate_id in map_layer_ids:
        _ensure_layer_visible(candidate_id)
    rect = _with_margin(_layer_extent_in_target_crs(layer, target_crs), margin_percent)
    if rect.isNull() or rect.isEmpty():
        raise ValidationError("INVALID_EXTENT", "Layer extent is invalid.", {"layer_id": layer_id})
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "item_id": item_id, "layer_id": layer_id, "layer_ids": map_layer_ids, "extent": _rect_to_dict(rect), "dimensions": {"x": x, "y": y, "width": width, "height": height}, "layer_visibility_ensured": layer_visibility_changed, "warnings": _warnings_for_layer(layer)}
    layout = _layout(layout_name)
    imports = _imports()
    item = imports["QgsLayoutItemMap"](layout)
    item.setId(str(item_id))
    try:
        item.setCrs(target_crs or project().crs())
    except Exception:
        pass
    item.setExtent(rect)
    try:
        item.setLayers(map_layers)
    except Exception:
        pass
    try:
        item.setFrameEnabled(True)
    except Exception:
        pass
    _position_item(item, x, y, width, height)
    layout.addLayoutItem(item)
    item.refresh()
    try:
        layout.refresh()
    except Exception:
        pass
    return {"layout_name": layout_name, "item_id": item_id, "layer_id": layer_id, "layer_ids": map_layer_ids, "extent": _rect_to_dict(rect), "dimensions": {"x": x, "y": y, "width": width, "height": height}, "layer_visibility_ensured": layer_visibility_changed, "warnings": _warnings_for_layer(layer)}


def set_layout_extent(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    item_id = require_param(params, "map_item_id", str)
    target_crs = _target_map_crs(params)
    if "layer_id" in params:
        base_layer = _layer(str(params["layer_id"]))
        rect = _layer_extent_in_target_crs(base_layer, target_crs)
    else:
        base_layer = None
        rect = _extent_from_params(params)
    rect = _with_margin(rect, float(params.get("margin_percent", 0)))
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "map_item_id": item_id, "extent": _rect_to_dict(rect)}
    layout = _layout(layout_name)
    item = _map_item(layout, item_id)
    layer = None
    if "layer_id" in params:
        layer = base_layer or _layer(str(params["layer_id"]))
        _ensure_layer_visible(str(params["layer_id"]))
        try:
            item.setCrs(target_crs or project().crs())
        except Exception:
            pass
        raw_layer_ids = params.get("layer_ids", params.get("map_layer_ids"))
        if raw_layer_ids:
            if isinstance(raw_layer_ids, str):
                raw_layer_ids = [raw_layer_ids]
            try:
                item.setLayers([_layer(str(candidate_id)) for candidate_id in raw_layer_ids])
            except Exception:
                pass
        else:
            try:
                current_layers = item.layers()
            except Exception:
                current_layers = []
            if not current_layers:
                try:
                    item.setLayers([layer])
                except Exception:
                    pass
    item.setExtent(rect)
    item.refresh()
    try:
        layout.refresh()
    except Exception:
        pass
    return {"layout_name": layout_name, "map_item_id": item_id, "extent": _rect_to_dict(rect), "layer_id": params.get("layer_id"), "layer_visibility_ensured": bool(layer)}


def add_layout_label(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    text = require_param(params, "text", str)
    item_id = params.get("item_id", "label")
    x = float(params.get("x", 10))
    y = float(params.get("y", 8))
    width = float(params.get("width", 190))
    height = float(params.get("height", 12))
    font_size = int(params.get("font_size", 12))
    bold = bool(params.get("bold", False))
    align = str(params.get("align", "left")).lower()
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "item_id": item_id, "text": text}
    imports = _imports()
    layout = _layout(layout_name)
    item = imports["QgsLayoutItemLabel"](layout)
    item.setId(str(item_id))
    item.setText(text)
    font = imports["QFont"]()
    font.setPointSize(font_size)
    font.setBold(bold)
    item.setFont(font)
    if align == "center":
        try:
            from qgis.PyQt.QtCore import Qt  # type: ignore

            item.setHAlign(Qt.AlignHCenter)
        except Exception:
            pass
    _position_item(item, x, y, width, height)
    layout.addLayoutItem(item)
    item.refresh()
    return {"layout_name": layout_name, "item_id": item_id, "text": text, "font_size": font_size, "bold": bold}


def add_layout_legend(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    item_id = params.get("item_id", "legend")
    title = params.get("title", "Legenda")
    linked_map_id = params.get("linked_map_item_id", "main_map")
    linked_layer_ids = params.get("linked_layer_ids", params.get("legend_layers", []))
    filter_to_map_layers = bool(params.get("filter_to_map_layers", False))
    x = float(params.get("x", 205))
    y = float(params.get("y", 25))
    width = float(params.get("width", 70))
    height = float(params.get("height", 100))
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "item_id": item_id, "linked_map_item_id": linked_map_id, "linked_layer_ids": linked_layer_ids, "filter_to_map_layers": filter_to_map_layers}
    imports = _imports()
    layout = _layout(layout_name)
    warnings: list[str] = []
    legend = imports["QgsLayoutItemLegend"](layout)
    legend.setId(str(item_id))
    legend.setTitle(str(title))
    try:
        map_item = _map_item(layout, str(linked_map_id))
        legend.setLinkedMap(map_item)
    except ValidationError as exc:
        map_item = None
        warnings.append(str(exc))
    filtered_layers = []
    if linked_layer_ids:
        if not isinstance(linked_layer_ids, list):
            linked_layer_ids = [linked_layer_ids]
        for layer_id in linked_layer_ids:
            layer = project().mapLayer(str(layer_id))
            if layer is not None:
                filtered_layers.append(layer)
            else:
                warnings.append(f"Legend layer not found: {layer_id}")
    elif filter_to_map_layers and map_item is not None:
        try:
            filtered_layers = list(map_item.layers())
        except Exception as exc:
            warnings.append(f"Could not read linked map layers for legend filtering: {exc}")
    if filtered_layers:
        try:
            legend.setAutoUpdateModel(False)
            root = legend.model().rootGroup()
            root.removeAllChildren()
            for layer in filtered_layers:
                root.addLayer(layer)
        except Exception as exc:
            warnings.append(f"Could not filter legend layers: {exc}")
    try:
        legend.refresh()
    except Exception:
        pass
    _position_item(legend, x, y, width, height)
    layout.addLayoutItem(legend)
    return {"layout_name": layout_name, "item_id": item_id, "title": title, "linked_map_item_id": linked_map_id, "legend_layer_ids": [layer.id() for layer in filtered_layers], "warnings": warnings}


def add_layout_scale_bar(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    item_id = params.get("item_id", "scale_bar")
    linked_map_id = params.get("linked_map_item_id", "main_map")
    x = float(params.get("x", 10))
    y = float(params.get("y", 180))
    width = float(params.get("width", 60))
    height = float(params.get("height", 10))
    units = str(params.get("units", "km")).lower()
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "item_id": item_id, "linked_map_item_id": linked_map_id, "units": units}
    imports = _imports()
    layout = _layout(layout_name)
    map_item = _map_item(layout, str(linked_map_id))
    bar = imports["QgsLayoutItemScaleBar"](layout)
    bar.setId(str(item_id))
    bar.setLinkedMap(map_item)
    warnings = []
    geographic_map = False
    try:
        geographic_map = bool(map_item.crs().isValid() and map_item.crs().isGeographic())
    except Exception:
        geographic_map = False
    try:
        bar.setStyle("Single Box")
    except Exception:
        pass
    try:
        if geographic_map and units == "km":
            distance_degrees = getattr(imports["QgsUnitTypes"], "DistanceDegrees", None)
            if distance_degrees is not None:
                bar.setUnits(distance_degrees)
                bar.setUnitLabel("deg")
                try:
                    bar.setUnitsPerSegment(float(params.get("units_per_segment", 1)))
                except Exception:
                    pass
                units = "deg"
            warnings.append("Scale bar is linked to a geographic CRS map, so SIGMAI used degree units instead of a silent 0 km metric scale. Reproject to a projected CRS for publication metric scale accuracy.")
        elif units == "km":
            bar.setUnits(imports["QgsUnitTypes"].DistanceKilometers)
            bar.setUnitLabel("km")
            try:
                bar.setUnitsPerSegment(float(params.get("units_per_segment", 10)))
            except Exception:
                pass
        elif units in {"m", "meter", "meters"}:
            bar.setUnits(imports["QgsUnitTypes"].DistanceMeters)
            bar.setUnitLabel("m")
            try:
                bar.setUnitsPerSegment(float(params.get("units_per_segment", 1000)))
            except Exception:
                pass
    except Exception:
        pass
    bar.setNumberOfSegments(2)
    bar.setNumberOfSegmentsLeft(0)
    _position_item(bar, x, y, width, height)
    layout.addLayoutItem(bar)
    try:
        bar.update()
    except Exception:
        pass
    return {"layout_name": layout_name, "item_id": item_id, "linked_map_item_id": linked_map_id, "units": units, "warnings": warnings}


def add_layout_north_arrow(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    item_id = params.get("item_id", "north_arrow")
    x = float(params.get("x", 180))
    y = float(params.get("y", 28))
    width = float(params.get("width", 15))
    height = float(params.get("height", 20))
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "item_id": item_id, "fallback": "label"}
    imports = _imports()
    layout = _layout(layout_name)
    label = imports["QgsLayoutItemLabel"](layout)
    label.setId(str(item_id))
    label.setText("N\n↑")
    font = imports["QFont"]()
    font.setPointSize(16)
    font.setBold(True)
    label.setFont(font)
    _position_item(label, x, y, width, height)
    layout.addLayoutItem(label)
    label.refresh()
    return {"layout_name": layout_name, "item_id": item_id, "fallback": "label", "text": "N ↑"}


def _valid_hex(value: str) -> str:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValidationError("BAD_REQUEST", "Color must be a hex value like #00A86B.", {"color": value})
    return value


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


def _apply_symbol_layer_color(symbol: Any, fill: str, stroke: str, fill_opacity: float, stroke_opacity: float, stroke_width: float, outline_only: bool) -> None:
    """Apply per-symbol-layer opacity so boundaries can stay visible while fills remain subtle."""
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


def set_layer_style(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "set_layer_style requires a vector layer.", {"layer_id": layer.id()})
    fill = _valid_hex(str(params.get("fill_color", "#D8E1E8")))
    stroke = _valid_hex(str(params.get("stroke_color", "#075D68")))
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
            "stroke_width": stroke_width,
            "opacity": opacity,
            "fill_opacity": fill_opacity,
            "stroke_opacity": stroke_opacity,
            "outline_only": outline_only,
        }
    imports = _imports()
    geometry_type = layer.geometryType()
    if geometry_type == imports["QgsWkbTypes"].PointGeometry:
        symbol = imports["QgsMarkerSymbol"].createSimple({"color": fill, "outline_color": stroke, "outline_width": str(stroke_width)})
    elif geometry_type == imports["QgsWkbTypes"].LineGeometry:
        symbol = imports["QgsLineSymbol"].createSimple({"color": stroke, "line_width": str(stroke_width)})
    else:
        style = "no" if outline_only else "solid"
        symbol = imports["QgsFillSymbol"].createSimple({"color": fill, "style": style, "outline_color": stroke, "outline_width": str(stroke_width)})
        _apply_symbol_layer_color(symbol, fill, stroke, fill_opacity, stroke_opacity, stroke_width, outline_only)
    layer.setRenderer(imports["QgsSingleSymbolRenderer"](symbol))
    try:
        layer.setOpacity(opacity if geometry_type != imports["QgsWkbTypes"].PolygonGeometry else 1.0)
    except Exception:
        pass
    layer.triggerRepaint()
    return {
        "layer_id": layer.id(),
        "layer_name": layer.name(),
        "style_type": "single_symbol",
        "geometry_type": int(geometry_type),
        "fill_color": fill,
        "stroke_color": stroke,
        "stroke_width": stroke_width,
        "opacity": opacity,
        "fill_opacity": fill_opacity,
        "stroke_opacity": stroke_opacity,
        "outline_only": outline_only,
    }


def _safe_layout_name(title: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", title).strip("_") or "SIGMAI_Map"
    return text[:50]


def list_layout_templates(params: dict[str, Any], context: dict[str, Any]):
    return {
        "templates": [
            {"name": name, "description": data["description"], "status": "enabled"}
            for name, data in LAYOUT_TEMPLATES.items()
        ],
        "style_profiles": sorted(STYLE_PROFILES),
    }


def choose_style_profile(params: dict[str, Any], context: dict[str, Any]):
    profile = str(params.get("style_profile", "scientific_soft"))
    if profile not in STYLE_PROFILES:
        profile = "scientific_soft"
    return {"style_profile": profile, "style": STYLE_PROFILES[profile]}


def apply_cartographic_palette(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    profile = choose_style_profile(params, context)["style_profile"]
    style = dict(STYLE_PROFILES[profile])
    style["layer_id"] = layer_id
    return set_layer_style(style, context)


def _template(name: str) -> dict[str, Any]:
    return LAYOUT_TEMPLATES.get(name, LAYOUT_TEMPLATES["scientific_basic"])


def _default_logo_path() -> str:
    path = Path(__file__).resolve().parents[1] / "icons" / "sigmai_logo_full.png"
    return str(path) if path.exists() else ""


PLUGIN_AUTHOR = "MACIEL, L. S. C."
PLUGIN_AUTHOR_EMAIL = "herpetomantiqueira@gmail.com"
CREATED_WITH = "SIGMAI - Secure GIS-AI Interface"


def build_product_credit(params: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Separate plugin authorship from user/map product authorship."""
    context = context or {}
    user_profile = context.get("user_profile") if isinstance(context.get("user_profile"), dict) else read_user_profile()
    project_metadata = context.get("project_metadata") if isinstance(context.get("project_metadata"), dict) else {}
    dev_mode = bool(params.get("dev_mode") or context.get("developer_mode"))
    use_plugin_author_in_dev = bool(params.get("use_plugin_author_as_map_author_in_dev", user_profile.get("use_plugin_author_as_map_author_in_dev", False)))
    map_author = str(params.get("map_author") or user_profile.get("default_map_author") or project_metadata.get("author") or "").strip()
    if not map_author and dev_mode and use_plugin_author_in_dev:
        map_author = PLUGIN_AUTHOR
    map_author_email = str(params.get("map_author_email") or user_profile.get("default_map_author_email") or "").strip()
    organization = str(params.get("organization") or user_profile.get("default_organization") or "").strip()
    data_source = str(params.get("data_source") or params.get("source") or "").strip()
    created_with = str(params.get("created_with") or CREATED_WITH).strip()
    if params.get("source_text"):
        credit_line = str(params["source_text"])
    elif user_profile.get("default_credit_line"):
        credit_line = str(user_profile["default_credit_line"])
    else:
        parts = []
        if data_source:
            parts.append(f"Fonte: {data_source}.")
        if map_author:
            parts.append(f"Elaboracao: {map_author}.")
        if organization:
            parts.append(f"Organizacao: {organization}.")
        parts.append(f"Elaborado com {created_with}/QGIS.")
        credit_line = " ".join(parts)
    if not map_author and PLUGIN_AUTHOR in credit_line and not (dev_mode and use_plugin_author_in_dev):
        credit_line = credit_line.replace(f"Elaboracao: {PLUGIN_AUTHOR}.", "").replace(f"Author: {PLUGIN_AUTHOR}", "").strip()
    return {
        "map_author": map_author,
        "map_author_email": map_author_email,
        "organization": organization,
        "data_source": data_source,
        "created_with": created_with,
        "plugin_author": PLUGIN_AUTHOR,
        "plugin_author_email": PLUGIN_AUTHOR_EMAIL,
        "credit_line": credit_line,
        "dev_mode": dev_mode,
    }


def _quality_grade(assessment: dict[str, Any]) -> dict[str, Any]:
    if assessment.get("grade") == "A":
        return {"grade": "A", "label": "Professional map"}
    if assessment.get("grade") == "B":
        return {"grade": "B", "label": "Usable technical map"}
    if assessment.get("grade") == "C":
        return {"grade": "C", "label": "Incomplete map"}
    if assessment.get("grade") == "D":
        return {"grade": "D", "label": "Likely flawed map"}
    return {"grade": "E", "label": "Failed/blank"}


def generate_professional_map(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    title = str(params.get("title", "SIGMAI Professional Map"))
    subtitle = str(params.get("subtitle", "SIGMAI - Secure GIS-AI Interface"))
    output_path = normalize_output_path(require_param(params, "output_path", str))
    fmt = str(params.get("format", output_path.suffix.lstrip(".") or "pdf")).lower()
    confirm_overwrite = bool(params.get("confirm_overwrite", False))
    template_name = str(params.get("layout_template", "scientific_publication"))
    template = _template(template_name)
    profile = str(params.get("style_profile", "scientific_soft"))
    if profile not in STYLE_PROFILES:
        profile = "scientific_soft"
    if fmt not in {"pdf", "png"}:
        raise ValidationError("BAD_REQUEST", "generate_professional_map supports pdf and png.", {"format": fmt})
    ensure_parent_exists(output_path)
    try:
        reject_existing_path_without_confirmation(output_path, confirm_overwrite)
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc
    layout_name = str(params.get("layout_name") or _safe_layout_name(title))
    if project().layoutManager().layoutByName(layout_name) is not None:
        layout_name = f"{layout_name}_{len(project().layoutManager().layouts()) + 1}"
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "layout_name": layout_name,
            "template": template_name,
            "style_profile": profile,
            "output_path": str(output_path),
            "items_planned": ["main_map", "title", "subtitle", "legend", "scale_bar", "north_arrow", "source", "logo"],
            "credits": build_product_credit(params, context),
        }
    imports = _imports()
    layout = imports["QgsPrintLayout"](project())
    layout.initializeDefaults()
    layout.setName(layout_name)
    project().layoutManager().addLayout(layout)
    if bool(params.get("apply_default_style", True)) and _is_vector_layer_id(layer_id):
        style = dict(STYLE_PROFILES[profile])
        style["layer_id"] = layer_id
        set_layer_style(style, context)
    items_created: list[str] = []
    map_layer_ids = params.get("map_layer_ids", params.get("layer_ids", [layer_id]))
    if isinstance(map_layer_ids, str):
        map_layer_ids = [map_layer_ids]
    if layer_id not in map_layer_ids:
        map_layer_ids.append(layer_id)
    map_crs = str(params.get("map_crs", "")).strip()
    map_payload = {"layout_name": layout_name, "layer_id": layer_id, "layer_ids": map_layer_ids, "item_id": "main_map", **template["map"], "margin_percent": 5}
    if map_crs:
        map_payload["map_crs"] = map_crs
    map_response = add_layout_map(map_payload, context)
    items_created.append("main_map")
    add_layout_label({"layout_name": layout_name, "item_id": "title", "text": title, "bold": True, "align": "center", **template["title"]}, context)
    items_created.append("title")
    add_layout_label({"layout_name": layout_name, "item_id": "subtitle", "text": subtitle, "align": "center", **template["subtitle"]}, context)
    items_created.append("subtitle")
    if bool(params.get("include_legend", True)):
        legend_layers = params.get("legend_layers") or [layer_id]
        add_layout_legend({"layout_name": layout_name, "item_id": "legend", "title": str(params.get("legend_title", "Legenda")), "linked_map_item_id": "main_map", "legend_layers": legend_layers, "filter_to_map_layers": True, **template["legend"]}, context)
        items_created.append("legend")
    if bool(params.get("include_scale_bar", True)):
        add_layout_scale_bar({"layout_name": layout_name, "item_id": "scale_bar", "linked_map_item_id": "main_map", "units": "km", "units_per_segment": params.get("units_per_segment", 1), **template["scale"]}, context)
        items_created.append("scale_bar")
    if bool(params.get("include_north_arrow", True)):
        add_layout_north_arrow({"layout_name": layout_name, "item_id": "north_arrow", **template["north"]}, context)
        items_created.append("north_arrow")
    if bool(params.get("include_grid", True)):
        grid_response = add_layout_grid({"layout_name": layout_name, "map_item_id": "main_map"}, context)
        items_created.append("grid" if grid_response.get("applied") else "grid_attempted")
    if bool(params.get("include_source", True)) or bool(params.get("include_authorship", True)):
        credits = build_product_credit(params, context)
        source = credits["credit_line"]
        add_layout_label({"layout_name": layout_name, "item_id": "source", "text": source, **template["source"]}, context)
        items_created.append("source")
    if bool(params.get("include_logo", True)):
        logo_path = str(params.get("logo_path") or _default_logo_path())
        if logo_path:
            try:
                add_layout_picture({"layout_name": layout_name, "item_id": "sigmai_logo", "path": logo_path, **template["logo"]}, context)
                items_created.append("logo")
            except Exception:
                pass
    extent_payload = {"layout_name": layout_name, "map_item_id": "main_map", "layer_id": layer_id, "layer_ids": map_layer_ids, "margin_percent": float(params.get("margin_percent", 5))}
    if map_crs:
        extent_payload["map_crs"] = map_crs
    extent_response = set_layout_extent(extent_payload, context)
    try:
        map_item = _map_item(layout, "main_map")
        map_item.setLayers([_layer(candidate_id) for candidate_id in map_layer_ids])
        map_item.refresh()
        layout.refresh()
    except Exception:
        pass
    export_result = export_layout({"layout_name": layout_name, "format": fmt, "path": str(output_path), "confirm_overwrite": confirm_overwrite}, context)
    assessment = evaluate_layout_cartographic_completeness(layout_name, str(output_path))
    quality = evaluate_map_quality({"layout_name": layout_name, "output_path": str(output_path)}, context)
    return {
        "layout_name": layout_name,
        "template": template_name,
        "style_profile": profile,
        "output_path": str(output_path),
        "format": fmt,
        "items_created": items_created,
        "credits": build_product_credit(params, context),
        "map_item": map_response,
        "extent": extent_response,
        "map_layer_ids": map_layer_ids,
        "legend_layers": params.get("legend_layers") or [layer_id],
        "export": export_result,
        "cartographic_assessment": assessment,
        "map_quality": quality,
    }


def evaluate_map_quality(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    output_path = params.get("output_path")
    assessment = evaluate_layout_cartographic_completeness(layout_name, str(output_path) if output_path else None)
    grade = _quality_grade(assessment)
    missing = assessment.get("missing_elements", [])
    if "valid_output" in missing or not assessment.get("output_ok", False):
        grade = {"grade": "E", "label": "Failed/blank"}
    elif "visible_map_render" in missing:
        grade = {"grade": "D", "label": "Likely flawed map"}
    elif "valid_map_extent" in missing:
        grade = {"grade": "C", "label": "Incomplete map"}
    warnings = []
    if "legend" in missing:
        warnings.append("Legend is missing.")
    if "scale_bar" in missing:
        warnings.append("Scale bar is missing.")
    if "visible_map_render" in missing:
        warnings.append("PNG visual analysis suggests the map body is blank or too weak.")
    return {
        "layout_name": layout_name,
        "output_path": str(output_path or ""),
        **grade,
        "command_success": True,
        "export_success": bool(assessment.get("output_ok", False)),
        "visual_success": assessment.get("visible_map_render_ok") is not False,
        "cartographic_quality": grade["grade"],
        "base_assessment": assessment,
        "warnings": warnings,
    }


def validate_map_readability(params: dict[str, Any], context: dict[str, Any]):
    return evaluate_map_quality(params, context)


def detect_visual_collisions(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    layout = _layout(layout_name)
    boxes = []
    collisions = []
    for item in layout.items():
        item_id = item.id() if hasattr(item, "id") else ""
        if not item_id:
            continue
        rect = item.sceneBoundingRect()
        current = {"item_id": item_id, "left": rect.left(), "top": rect.top(), "right": rect.right(), "bottom": rect.bottom()}
        for previous in boxes:
            if not (current["right"] <= previous["left"] or current["left"] >= previous["right"] or current["bottom"] <= previous["top"] or current["top"] >= previous["bottom"]):
                collisions.append({"a": previous["item_id"], "b": item_id})
        boxes.append(current)
    return {"layout_name": layout_name, "collisions": collisions, "collision_count": len(collisions)}


def suggest_layout_improvements(params: dict[str, Any], context: dict[str, Any]):
    quality = evaluate_map_quality(params, context)
    suggestions = []
    missing = quality.get("base_assessment", {}).get("missing_elements", [])
    if missing:
        suggestions.append(f"Add or repair missing elements: {', '.join(missing)}")
    if quality.get("grade") not in {"A+", "A"}:
        suggestions.append("Use generate_professional_map with scientific_publication template and legend_layers.")
    return {"quality": quality, "suggestions": suggestions}


def generate_basic_map(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    title = str(params.get("title", "SIGMAI Test Map"))
    output_path = normalize_output_path(require_param(params, "output_path", str))
    fmt = str(params.get("format", output_path.suffix.lstrip(".") or "pdf")).lower()
    confirm_overwrite = bool(params.get("confirm_overwrite", False))
    if fmt not in {"pdf", "png"}:
        raise ValidationError("BAD_REQUEST", "generate_basic_map supports pdf and png.", {"format": fmt})
    ensure_parent_exists(output_path)
    try:
        reject_existing_path_without_confirmation(output_path, confirm_overwrite)
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc
    layout_name = str(params.get("layout_name") or _safe_layout_name(title))
    if project().layoutManager().layoutByName(layout_name) is not None:
        layout_name = f"{layout_name}_{len(project().layoutManager().layouts()) + 1}"
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "output_path": str(output_path), "items_planned": ["main_map", "title", "legend", "scale_bar", "north_arrow", "source"], "credits": build_product_credit(params, context)}
    imports = _imports()
    layout = imports["QgsPrintLayout"](project())
    layout.initializeDefaults()
    layout.setName(layout_name)
    project().layoutManager().addLayout(layout)
    if bool(params.get("apply_default_style", True)) and _is_vector_layer_id(layer_id):
        set_layer_style({"layer_id": layer_id}, context)
    items_created = []
    add_layout_map({"layout_name": layout_name, "layer_id": layer_id, "item_id": "main_map", "x": 10, "y": 25, "width": 180, "height": 145, "margin_percent": 5}, context)
    items_created.append("main_map")
    add_layout_label({"layout_name": layout_name, "item_id": "title", "text": title, "x": 10, "y": 8, "width": 260, "height": 12, "font_size": 16, "bold": True, "align": "center"}, context)
    items_created.append("title")
    if bool(params.get("include_legend", True)):
        add_layout_legend({"layout_name": layout_name, "item_id": "legend", "title": "Legenda", "x": 200, "y": 25, "width": 75, "height": 90, "linked_map_item_id": "main_map"}, context)
        items_created.append("legend")
    if bool(params.get("include_scale_bar", True)):
        add_layout_scale_bar({"layout_name": layout_name, "item_id": "scale_bar", "linked_map_item_id": "main_map", "x": 15, "y": 175, "width": 65, "height": 10, "units": "km"}, context)
        items_created.append("scale_bar")
    if bool(params.get("include_north_arrow", True)):
        add_layout_north_arrow({"layout_name": layout_name, "item_id": "north_arrow", "x": 180, "y": 28, "width": 15, "height": 20}, context)
        items_created.append("north_arrow")
    if bool(params.get("include_source", True)):
        source = build_product_credit(params, context)["credit_line"]
        add_layout_label({"layout_name": layout_name, "item_id": "source", "text": source, "x": 10, "y": 190, "width": 260, "height": 8, "font_size": 8}, context)
        items_created.append("source")
    export_result = export_layout({"layout_name": layout_name, "format": fmt, "path": str(output_path), "confirm_overwrite": confirm_overwrite}, context)
    assessment = evaluate_layout_cartographic_completeness(layout_name, str(output_path))
    return {"layout_name": layout_name, "output_path": str(output_path), "format": fmt, "items_created": items_created, "credits": build_product_credit(params, context), "export": export_result, "cartographic_assessment": assessment}


def evaluate_layout_cartographic_completeness(layout_name: str, output_path: str | None = None) -> dict[str, Any]:
    layout = _layout(layout_name)
    items = {}
    for item in layout.items():
        try:
            item_id = item.id()
        except Exception:
            continue
        if item_id:
            items[item_id] = item
    missing = []
    for required in ["main_map", "title", "legend", "scale_bar", "north_arrow", "source"]:
        if required not in items:
            missing.append(required)
    output_ok = False
    output_size = 0
    if output_path:
        path = Path(output_path)
        if path.exists():
            output_size = path.stat().st_size
        min_size = 10000 if path.suffix.lower() == ".png" else 5000
        output_ok = path.exists() and output_size >= min_size
        if not output_ok:
            missing.append("valid_output")
    map_ok = False
    if "main_map" in items:
        map_item = items["main_map"]
        for method_name in ("extent", "requestedExtent", "visibleExtent"):
            if hasattr(map_item, method_name):
                try:
                    rect = getattr(map_item, method_name)()
                    if rect is not None and not rect.isEmpty():
                        map_ok = True
                        break
                except Exception:
                    pass
    if not map_ok:
        missing.append("valid_map_extent")
    visible_map_ok = None
    if output_path and "main_map" in items:
        visible_map_ok = _png_map_area_has_content(layout, items["main_map"], Path(output_path))
        if visible_map_ok is False:
            missing.append("visible_map_render")
    if not missing:
        grade = "A"
        label = "Complete basic cartographic map"
    elif len(missing) <= 2 and output_ok and map_ok:
        grade = "B"
        label = "Usable map with minor missing elements"
    elif output_ok:
        grade = "C"
        label = "Layout generated but not cartographically complete"
    else:
        grade = "D"
        label = "Layout/export technically succeeded but likely blank"
    return {"grade": grade, "label": label, "missing_elements": sorted(set(missing)), "output_ok": output_ok, "output_size": output_size, "map_extent_ok": map_ok, "visible_map_render_ok": visible_map_ok}


def _png_map_area_has_content(layout: Any, map_item: Any, output_path: Path) -> bool | None:
    if output_path.suffix.lower() != ".png" or not output_path.exists():
        return None
    try:
        image = _imports()["QImage"](str(output_path))
        if image.isNull():
            return False
        page = layout.pageCollection().page(0)
        page_rect = page.rect()
        item_rect = map_item.sceneBoundingRect()
        sx = image.width() / float(page_rect.width())
        sy = image.height() / float(page_rect.height())
        left = max(0, int(item_rect.left() * sx))
        top = max(0, int(item_rect.top() * sy))
        right = min(image.width(), int(item_rect.right() * sx))
        bottom = min(image.height(), int(item_rect.bottom() * sy))
        if right <= left or bottom <= top:
            return False
        step_x = max(1, (right - left) // 120)
        step_y = max(1, (bottom - top) // 120)
        non_blank = 0
        sampled = 0
        for y in range(top, bottom, step_y):
            for x in range(left, right, step_x):
                color = image.pixelColor(x, y)
                if color.alpha() > 0:
                    sampled += 1
                    if not (color.red() > 245 and color.green() > 245 and color.blue() > 245):
                        non_blank += 1
        return sampled > 0 and (non_blank / sampled) > 0.01
    except Exception:
        return None


def evaluate_layout_cartographic_completeness_command(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    layout_name = require_param(params, "layout_name", str)
    output_path = params.get("output_path")
    return evaluate_layout_cartographic_completeness(layout_name, str(output_path) if output_path else None)


def generate_workflow_report(params: dict[str, Any], context: dict[str, Any]):
    output_value = params.get("output_path", "")
    include_logs = bool(params.get("include_logs", True))
    logger = context.get("logger")
    logs = logger.tail(200) if logger and include_logs else []
    qgs_project = project()
    layers = []
    for layer in qgs_project.mapLayers().values():
        layers.append({"id": layer.id(), "name": layer.name(), "type": layer_type_name(layer), "crs": crs_authid(layer.crs()) if hasattr(layer, "crs") else "", "feature_count": int(layer.featureCount()) if layer_type_name(layer) == "vector" else None, "extent": extent_to_dict(layer)})
    layouts = [layout.name() for layout in qgs_project.layoutManager().layouts()]
    outputs = []
    root = Path(__file__).resolve().parents[2] / "test_outputs"
    if root.exists():
        for path in sorted(root.glob("*")):
            if path.is_file() and path.suffix.lower() in {".pdf", ".png", ".gpkg", ".md", ".json"}:
                outputs.append({"path": str(path), "size": path.stat().st_size})
    credits = build_product_credit(params, context)
    summary = {"product": "SIGMAI — Secure GIS-AI Interface", "qgis_version": context.get("qgis_version"), "plugin_version": context.get("plugin_version", "0.2.0"), "host": context.get("host"), "port": context.get("port"), "project_crs": crs_authid(qgs_project.crs()), "layer_count": len(layers), "layout_count": len(layouts), "recent_log_count": len(logs), "output_count": len(outputs), "plugin_author": credits["plugin_author"], "map_author": credits["map_author"] or "not specified"}
    if context.get("dry_run"):
        return {"dry_run": True, "summary": summary, "credits": credits, "would_write": output_value}
    markdown = ["# SIGMAI Workflow Report", "", "## Environment", ""]
    for key, value in summary.items():
        markdown.append(f"- {key}: `{value}`")
    markdown.extend(["", "## Layers", ""])
    for layer in layers:
        markdown.append(f"- `{layer['name']}` ({layer['type']}): CRS `{layer['crs']}`, features `{layer['feature_count']}`")
    markdown.extend(["", "## Layouts", ""])
    for layout_name in layouts:
        markdown.append(f"- `{layout_name}`")
    markdown.extend(["", "## Outputs", ""])
    for output in outputs:
        markdown.append(f"- `{output['path']}` ({output['size']} bytes)")
    markdown.extend(["", "## Security", "", "- Local only: 127.0.0.1", "- Token protected", "- No arbitrary Python execution", "", "## Authorship and Credits", "", f"- Plugin author: {credits['plugin_author']} ({credits['plugin_author_email']})", f"- Map author: {credits['map_author'] or 'not specified'}", f"- Map author email: {credits['map_author_email'] or 'not specified'}", f"- Organization: {credits['organization'] or 'not specified'}", f"- Data source: {credits['data_source'] or 'not specified'}", f"- Created with: {credits['created_with']}/QGIS", "- Associated project of the plugin: Herpeto Mantiqueira"])
    output_path = ""
    if output_value:
        path = normalize_output_path(str(output_value))
        ensure_parent_exists(path)
        try:
            reject_existing_path_without_confirmation(path, bool(params.get("confirm_overwrite", False)))
        except FileExistsError as exc:
            raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(path)}) from exc
        path.write_text("\n".join(markdown), encoding="utf-8")
        output_path = str(path)
    return {"summary": summary, "credits": credits, "output_path": output_path, "layers": layers, "layouts": layouts, "outputs": outputs[:50]}


# Canonical definitions kept at the end so they override early compatibility
# implementations when QGIS reloads this module.
def add_layout_north_arrow(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    item_id = params.get("item_id", "north_arrow")
    x = float(params.get("x", 180))
    y = float(params.get("y", 28))
    width = float(params.get("width", 15))
    height = float(params.get("height", 20))
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "item_id": item_id, "fallback": "label"}
    imports = _imports()
    layout = _layout(layout_name)
    label = imports["QgsLayoutItemLabel"](layout)
    label.setId(str(item_id))
    label.setText("N\n^")
    font = imports["QFont"]()
    font.setPointSize(16)
    font.setBold(True)
    label.setFont(font)
    _position_item(label, x, y, width, height)
    layout.addLayoutItem(label)
    label.refresh()
    return {"layout_name": layout_name, "item_id": item_id, "fallback": "label", "text": "N ^"}


def add_layout_grid(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    map_item_id = params.get("map_item_id", "main_map")
    enabled = bool(params.get("enabled", True))
    interval_x = params.get("interval_x")
    interval_y = params.get("interval_y")
    show_annotations = bool(params.get("show_annotations", True))
    line_color = _valid_hex(str(params.get("line_color", "#6B7A86")))
    line_width = float(params.get("line_width", 0.15))
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "map_item_id": map_item_id, "enabled": enabled, "interval_x": interval_x, "interval_y": interval_y, "show_annotations": show_annotations}
    imports = _imports()
    layout = _layout(layout_name)
    map_item = _map_item(layout, str(map_item_id))
    warnings: list[str] = []
    try:
        grid = map_item.grid()
    except Exception:
        grid = None
        warnings.append("QGIS map grid API was not available for this map item.")
    if grid is None:
        return {"layout_name": layout_name, "map_item_id": map_item_id, "enabled": False, "warnings": warnings}
    try:
        grid.setEnabled(enabled)
    except Exception as exc:
        warnings.append(f"Could not enable map grid: {exc}")
    if interval_x is not None:
        try:
            grid.setIntervalX(float(interval_x))
        except Exception as exc:
            warnings.append(f"Could not set grid interval_x: {exc}")
    if interval_y is not None:
        try:
            grid.setIntervalY(float(interval_y))
        except Exception as exc:
            warnings.append(f"Could not set grid interval_y: {exc}")
    try:
        grid.setAnnotationEnabled(show_annotations)
    except Exception:
        warnings.append("Grid annotations are not available in this QGIS API variant.")
    try:
        grid.setGridLineColor(imports["QColor"](line_color))
    except Exception:
        warnings.append("Grid line color could not be applied.")
    try:
        grid.setGridLineWidth(line_width)
    except Exception:
        warnings.append("Grid line width could not be applied.")
    try:
        map_item.refresh()
    except Exception:
        pass
    return {"layout_name": layout_name, "map_item_id": map_item_id, "enabled": enabled, "interval_x": interval_x, "interval_y": interval_y, "show_annotations": show_annotations, "warnings": warnings}


def add_layout_picture(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    picture_path = Path(require_param(params, "path", str)).expanduser()
    item_id = params.get("item_id", "picture")
    x = float(params.get("x", 235))
    y = float(params.get("y", 175))
    width = float(params.get("width", 35))
    height = float(params.get("height", 12))
    if picture_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".svg"}:
        raise ValidationError("BAD_REQUEST", "Picture path must be a PNG, JPG, JPEG or SVG file.", {"path": str(picture_path)})
    if not picture_path.exists() or not picture_path.is_file():
        raise ValidationError("FILE_NOT_FOUND", "Picture file was not found.", {"path": str(picture_path)})
    if context.get("dry_run"):
        return {"dry_run": True, "layout_name": layout_name, "item_id": item_id, "path": str(picture_path), "dimensions": {"x": x, "y": y, "width": width, "height": height}}
    imports = _imports()
    layout = _layout(layout_name)
    picture = imports["QgsLayoutItemPicture"](layout)
    picture.setId(str(item_id))
    picture.setPicturePath(str(picture_path))
    _position_item(picture, x, y, width, height)
    layout.addLayoutItem(picture)
    try:
        picture.refreshPicture()
    except Exception:
        pass
    return {"layout_name": layout_name, "item_id": item_id, "path": str(picture_path), "dimensions": {"x": x, "y": y, "width": width, "height": height}}


def generate_basic_map(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    title = str(params.get("title", "SIGMAI Test Map"))
    output_path = normalize_output_path(require_param(params, "output_path", str))
    fmt = str(params.get("format", output_path.suffix.lstrip(".") or "pdf")).lower()
    confirm_overwrite = bool(params.get("confirm_overwrite", False))
    if fmt not in {"pdf", "png"}:
        raise ValidationError("BAD_REQUEST", "generate_basic_map supports pdf and png.", {"format": fmt})
    ensure_parent_exists(output_path)
    try:
        reject_existing_path_without_confirmation(output_path, confirm_overwrite)
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc
    layout_name = str(params.get("layout_name") or _safe_layout_name(title))
    if project().layoutManager().layoutByName(layout_name) is not None:
        layout_name = f"{layout_name}_{len(project().layoutManager().layouts()) + 1}"
    include_grid = bool(params.get("include_grid", False))
    logo_path = str(params.get("logo_path", "")).strip()
    legend_layers = params.get("legend_layers", [layer_id])
    layout_template = str(params.get("layout_template", "basic"))
    scale_strategy = str(params.get("scale_strategy", "auto"))
    prefer_projected_scale = bool(params.get("prefer_projected_scale", True))
    if context.get("dry_run"):
        planned = ["main_map", "title", "legend", "scale_bar", "north_arrow", "source"]
        if include_grid:
            planned.append("grid")
        if logo_path:
            planned.append("logo")
        return {"dry_run": True, "layout_name": layout_name, "output_path": str(output_path), "items_planned": planned, "legend_layers": legend_layers, "layout_template": layout_template, "scale_strategy": scale_strategy, "credits": build_product_credit(params, context)}
    imports = _imports()
    layout = imports["QgsPrintLayout"](project())
    layout.initializeDefaults()
    layout.setName(layout_name)
    project().layoutManager().addLayout(layout)
    if bool(params.get("apply_default_style", True)) and _is_vector_layer_id(layer_id):
        set_layer_style({"layer_id": layer_id}, context)
    items_created = []
    add_layout_map({"layout_name": layout_name, "layer_id": layer_id, "item_id": "main_map", "x": 10, "y": 25, "width": 180, "height": 145, "margin_percent": 5}, context)
    items_created.append("main_map")
    if include_grid:
        add_layout_grid({"layout_name": layout_name, "map_item_id": "main_map", "enabled": True, "interval_x": params.get("grid_interval_x"), "interval_y": params.get("grid_interval_y")}, context)
        items_created.append("grid")
    add_layout_label({"layout_name": layout_name, "item_id": "title", "text": title, "x": 10, "y": 8, "width": 260, "height": 12, "font_size": 16, "bold": True, "align": "center"}, context)
    items_created.append("title")
    if bool(params.get("include_legend", True)):
        add_layout_legend({"layout_name": layout_name, "item_id": "legend", "title": "Legenda", "x": 205, "y": 25, "width": 70, "height": 90, "linked_map_item_id": "main_map", "legend_layers": legend_layers, "filter_to_map_layers": True}, context)
        items_created.append("legend")
    if bool(params.get("include_scale_bar", True)):
        add_layout_scale_bar({"layout_name": layout_name, "item_id": "scale_bar", "linked_map_item_id": "main_map", "x": 15, "y": 175, "width": 65, "height": 10, "units": "km", "units_per_segment": params.get("units_per_segment", 1)}, context)
        items_created.append("scale_bar")
    if bool(params.get("include_north_arrow", True)):
        add_layout_north_arrow({"layout_name": layout_name, "item_id": "north_arrow", "x": 188, "y": 28, "width": 10, "height": 16}, context)
        items_created.append("north_arrow")
    if logo_path:
        add_layout_picture({"layout_name": layout_name, "item_id": "logo", "path": logo_path, "x": 230, "y": 175, "width": 42, "height": 14}, context)
        items_created.append("logo")
    if bool(params.get("include_source", True)):
        source = build_product_credit(params, context)["credit_line"]
        add_layout_label({"layout_name": layout_name, "item_id": "source", "text": source, "x": 10, "y": 190, "width": 260, "height": 8, "font_size": 8}, context)
        items_created.append("source")
    set_layout_extent({"layout_name": layout_name, "map_item_id": "main_map", "layer_id": layer_id, "margin_percent": 5}, context)
    export_result = export_layout({"layout_name": layout_name, "format": fmt, "path": str(output_path), "confirm_overwrite": confirm_overwrite}, context)
    assessment = evaluate_layout_cartographic_completeness(layout_name, str(output_path))
    warnings = []
    try:
        if prefer_projected_scale and project().crs().isValid() and project().crs().isGeographic():
            warnings.append("Project CRS is geographic; metric scale bars may be approximate. Reproject to a projected CRS for publication scale accuracy.")
    except Exception:
        pass
    return {"layout_name": layout_name, "output_path": str(output_path), "format": fmt, "items_created": items_created, "credits": build_product_credit(params, context), "export": export_result, "cartographic_assessment": assessment, "legend_layers": legend_layers, "layout_template": layout_template, "scale_strategy": scale_strategy, "warnings": warnings}
