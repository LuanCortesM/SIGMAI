from __future__ import annotations

from pathlib import Path
from typing import Any

from ..security import normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param
from .common import crs_authid, extent_to_dict, layer_type_name, project
from .gis_tools import PROCESSING_ALLOWLIST, _processing_run, _serialize_processing_result


ALLOWED_RASTER_EXTENSIONS = {".tif", ".tiff", ".vrt", ".asc", ".img", ".jp2"}


def _raster_layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if layer_type_name(layer) != "raster":
        raise ValidationError("RASTER_LAYER_REQUIRED", "This command requires a raster layer.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_RASTER_LAYER", "Raster layer is invalid.", {"layer_id": layer_id})
    return layer


def _check_raster_output(output: str, confirm_overwrite: bool) -> str:
    if output == "TEMPORARY_OUTPUT":
        return output
    output_path = normalize_output_path(output)
    try:
        reject_existing_path_without_confirmation(output_path, confirm_overwrite)
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc
    if not output_path.parent.exists():
        raise ValidationError("BAD_REQUEST", "Output directory does not exist.", {"path": str(output_path.parent)})
    return str(output_path)


def _band_count(layer: Any) -> int:
    try:
        return int(layer.bandCount())
    except Exception:
        return 0


def _raster_units_warning(layer: Any) -> list[str]:
    warnings = []
    crs = layer.crs()
    if crs and crs.isValid() and crs.isGeographic():
        warnings.append("Raster CRS is geographic. Terrain and metric operations may need a projected CRS.")
    return warnings


def load_raster_layer(params: dict[str, Any], context: dict[str, Any]):
    path_value = require_param(params, "path", str)
    name = params.get("name") or Path(path_value).stem
    path = normalize_output_path(path_value)
    if not path.exists() or not path.is_file():
        raise ValidationError("FILE_NOT_FOUND", "Raster file was not found.", {"path": str(path)})
    if path.suffix.lower() not in ALLOWED_RASTER_EXTENSIONS:
        raise ValidationError("UNSUPPORTED_RASTER_FORMAT", "Unsupported raster format.", {"suffix": path.suffix})
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "would_load": str(path),
            "name": name,
            "changes": ["Add the raster layer to the current QGIS project without modifying the source file."],
        }
    try:
        from qgis.core import QgsRasterLayer  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc
    layer = QgsRasterLayer(str(path), str(name))
    if not layer.isValid():
        raise ValidationError("INVALID_RASTER_LAYER", "QGIS could not load this raster layer.", {"path": str(path)})
    project().addMapLayer(layer)
    return {
        "layer_id": layer.id(),
        "name": layer.name(),
        "path": str(path),
        "crs": crs_authid(layer.crs()),
        "band_count": _band_count(layer),
        "extent": extent_to_dict(layer),
        "valid": True,
    }


def raster_info(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    provider = layer.dataProvider()
    extent = extent_to_dict(layer)
    width = int(layer.width()) if hasattr(layer, "width") else None
    height = int(layer.height()) if hasattr(layer, "height") else None
    pixel_size = {}
    if extent and width and height:
        pixel_size = {
            "x": abs((extent["xmax"] - extent["xmin"]) / width) if width else None,
            "y": abs((extent["ymax"] - extent["ymin"]) / height) if height else None,
        }
    return {
        "layer_id": layer.id(),
        "name": layer.name(),
        "source": layer.source(),
        "provider": provider.name() if provider else "",
        "crs": crs_authid(layer.crs()),
        "extent": extent,
        "width": width,
        "height": height,
        "pixel_size": pixel_size,
        "band_count": _band_count(layer),
        "warnings": _raster_units_warning(layer),
    }


def raster_band_statistics(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    band = int(params.get("band", 1))
    if band < 1 or band > _band_count(layer):
        raise ValidationError("BAD_REQUEST", "band is outside raster band range.", {"band": band, "band_count": _band_count(layer)})
    provider = layer.dataProvider()
    try:
        stats = provider.bandStatistics(band)
    except Exception as exc:
        raise ValidationError("RASTER_STATS_FAILED", "QGIS failed to compute raster band statistics.", {"error": str(exc)}) from exc
    return {
        "layer_id": layer.id(),
        "band": band,
        "minimum": getattr(stats, "minimumValue", None),
        "maximum": getattr(stats, "maximumValue", None),
        "mean": getattr(stats, "mean", None),
        "std_dev": getattr(stats, "stdDev", None),
        "range": getattr(stats, "range", None),
    }


def raster_metadata_report(params: dict[str, Any], context: dict[str, Any]):
    info = raster_info(params, context)
    info["metadata"] = {
        "format_note": "Safe summary generated by SIGMAI without reading full raster values.",
        "recommended_next_steps": [
            "Use raster_band_statistics for numeric ranges.",
            "Use raster_hillshade or raster_slope only on suitable elevation rasters.",
            "Prefer projected CRS for metric terrain analysis.",
        ],
    }
    return info


def _run_raster_algorithm(params: dict[str, Any], context: dict[str, Any], algorithm: str, qgis_params: dict[str, Any]):
    if algorithm not in PROCESSING_ALLOWLIST:
        raise ValidationError("PROCESSING_ALGORITHM_BLOCKED", "Raster algorithm is not in the SIGMAI allowlist.", {"algorithm": algorithm})
    output = _check_raster_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    qgis_params["OUTPUT"] = output
    if context.get("dry_run"):
        serialized = {key: value.id() if hasattr(value, "id") else value for key, value in qgis_params.items()}
        return {"dry_run": True, "algorithm": algorithm, "parameters": serialized}
    result = _processing_run(algorithm, qgis_params)
    return {"algorithm": algorithm, "result": _serialize_processing_result(result)}


def raster_reproject(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    target_crs = require_param(params, "target_crs", str)
    return _run_raster_algorithm(params, context, "gdal:warpreproject", {"INPUT": layer, "TARGET_CRS": target_crs})


def raster_clip_by_extent(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    extent = require_param(params, "extent", str)
    return _run_raster_algorithm(params, context, "gdal:cliprasterbyextent", {"INPUT": layer, "PROJWIN": extent})


def raster_clip_by_mask(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    mask_layer_id = require_param(params, "mask_layer_id", str)
    mask = project().mapLayer(mask_layer_id)
    if mask is None:
        raise ValidationError("LAYER_NOT_FOUND", "Mask layer not found.", {"layer_id": mask_layer_id})
    return _run_raster_algorithm(params, context, "gdal:cliprasterbymasklayer", {"INPUT": layer, "MASK": mask})


def raster_slope(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    payload = _run_raster_algorithm(params, context, "gdal:slope", {"INPUT": layer, "BAND": int(params.get("band", 1))})
    payload.setdefault("warnings", []).extend(_raster_units_warning(layer))
    return payload


def raster_aspect(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    payload = _run_raster_algorithm(params, context, "gdal:aspect", {"INPUT": layer, "BAND": int(params.get("band", 1))})
    payload.setdefault("warnings", []).extend(_raster_units_warning(layer))
    return payload


def raster_hillshade(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    qgis_params = {
        "INPUT": layer,
        "BAND": int(params.get("band", 1)),
        "Z_FACTOR": float(params.get("z_factor", 1.0)),
        "AZIMUTH": float(params.get("azimuth", 315.0)),
        "ALTITUDE": float(params.get("altitude", 45.0)),
    }
    payload = _run_raster_algorithm(params, context, "gdal:hillshade", qgis_params)
    payload.setdefault("warnings", []).extend(_raster_units_warning(layer))
    return payload


def raster_contours(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    interval = float(params.get("interval", 10.0))
    if interval <= 0:
        raise ValidationError("BAD_REQUEST", "interval must be greater than zero.", {"interval": interval})
    return _run_raster_algorithm(params, context, "gdal:contour", {"INPUT": layer, "BAND": int(params.get("band", 1)), "INTERVAL": interval})


def raster_polygonize(params: dict[str, Any], context: dict[str, Any]):
    layer = _raster_layer(require_param(params, "layer_id", str))
    field_name = str(params.get("field_name", "DN"))
    return _run_raster_algorithm(params, context, "gdal:polygonize", {"INPUT": layer, "BAND": int(params.get("band", 1)), "FIELD": field_name})
