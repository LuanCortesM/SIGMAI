from __future__ import annotations

from pathlib import Path
from typing import Any

from ..security import normalize_output_path
from ..validators import ValidationError, require_param
from .common import project


ALLOWED_VECTOR_EXTENSIONS = {".shp", ".gpkg", ".geojson", ".json", ".kml", ".gpx"}


def handle(params: dict[str, Any], context: dict[str, Any]):
    path_value = require_param(params, "path", str)
    name = params.get("name") or Path(path_value).stem
    provider = params.get("provider", "ogr")
    if provider != "ogr":
        raise ValidationError("BAD_REQUEST", "Only provider 'ogr' is allowed for load_vector_layer.", {"provider": provider})

    path = normalize_output_path(path_value)
    if not path.exists() or not path.is_file():
        raise ValidationError("FILE_NOT_FOUND", "Vector file was not found.", {"path": str(path)})
    if path.suffix.lower() not in ALLOWED_VECTOR_EXTENSIONS:
        raise ValidationError("UNSUPPORTED_VECTOR_FORMAT", "Unsupported vector format.", {"suffix": path.suffix})

    if context.get("dry_run"):
        return {
            "dry_run": True,
            "would_load": str(path),
            "name": name,
            "provider": provider,
            "changes": ["Add the vector layer to the current QGIS project without modifying the source file."],
        }

    try:
        from qgis.core import QgsVectorLayer  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc

    layer = QgsVectorLayer(str(path), str(name), provider)
    if not layer.isValid():
        raise ValidationError("INVALID_VECTOR_LAYER", "QGIS could not load this vector layer.", {"path": str(path)})
    project().addMapLayer(layer)
    return {
        "layer_id": layer.id(),
        "name": layer.name(),
        "path": str(path),
        "provider": provider,
        "crs": layer.crs().authid() if layer.crs().isValid() else "",
        "valid": True,
    }
