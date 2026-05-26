from __future__ import annotations

from typing import Any


def qgis_imports() -> dict[str, Any]:
    try:
        from qgis.core import (  # type: ignore
            Qgis,
            QgsApplication,
            QgsMapLayer,
            QgsProject,
            QgsWkbTypes,
            QgsLayoutExporter,
        )
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc

    return {
        "Qgis": Qgis,
        "QgsApplication": QgsApplication,
        "QgsMapLayer": QgsMapLayer,
        "QgsProject": QgsProject,
        "QgsWkbTypes": QgsWkbTypes,
        "QgsLayoutExporter": QgsLayoutExporter,
    }


def project():
    imports = qgis_imports()
    return imports["QgsProject"].instance()


def crs_authid(crs: Any) -> str:
    if crs is None or not crs.isValid():
        return ""
    return crs.authid() or crs.description() or ""


def layer_type_name(layer: Any) -> str:
    imports = qgis_imports()
    qgs_map_layer = imports["QgsMapLayer"]
    if layer.type() == qgs_map_layer.VectorLayer:
        return "vector"
    if layer.type() == qgs_map_layer.RasterLayer:
        return "raster"
    return "unknown"


def layer_feature_count(layer: Any) -> int | None:
    try:
        if layer_type_name(layer) == "vector" and layer.isValid():
            return int(layer.featureCount())
    except Exception:
        return None
    return None


def extent_to_dict(layer: Any) -> dict[str, float] | None:
    try:
        extent = layer.extent()
        return {
            "xmin": extent.xMinimum(),
            "ymin": extent.yMinimum(),
            "xmax": extent.xMaximum(),
            "ymax": extent.yMaximum(),
        }
    except Exception:
        return None


def summarize_layer(layer: Any) -> dict[str, Any]:
    feature_count = layer_feature_count(layer)
    summary = {
        "id": layer.id(),
        "name": layer.name(),
        "type": layer_type_name(layer),
        "crs": crs_authid(layer.crs()) if hasattr(layer, "crs") else "",
        "valid": bool(layer.isValid()),
    }
    if feature_count is not None:
        summary["feature_count"] = feature_count
    return summary
