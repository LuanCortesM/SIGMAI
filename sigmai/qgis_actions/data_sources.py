from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from ..security import normalize_output_path
from ..validators import ValidationError, require_param
from .common import crs_authid, extent_to_dict, layer_type_name, project
from .load_layers import handle as load_vector_layer

MAX_SAFE_GPX_XML_BYTES = 25_000_000


def _safe_url(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("BAD_REQUEST", "Only http/https service URLs are accepted.", {"scheme": parsed.scheme})
    if parsed.username or parsed.password:
        raise ValidationError("CREDENTIALS_IN_URL_BLOCKED", "Credentials in service URLs are not allowed.", {})
    return {"scheme": parsed.scheme, "host": parsed.hostname or "", "path": parsed.path, "query_keys": sorted([part.split("=", 1)[0] for part in parsed.query.split("&") if part])}


def _safe_xml_root_from_file(path: Path) -> ET.Element:
    data = path.read_bytes()
    if len(data) > MAX_SAFE_GPX_XML_BYTES:
        raise ValidationError("XML_TOO_LARGE", "GPX XML exceeds the safe parsing limit.", {"path": str(path), "max_bytes": MAX_SAFE_GPX_XML_BYTES})
    probe = data[:4096].lower()
    if b"<!doctype" in probe or b"<!entity" in probe:
        raise ValidationError("UNSAFE_XML_BLOCKED", "GPX XML with DTD or entity declarations is blocked.", {"path": str(path)})
    return ET.fromstring(data)  # nosec B314 - size-limited GPX XML; DTD/entity declarations are rejected before parsing.


def inspect_data_source(params: dict[str, Any], context: dict[str, Any]):
    path = normalize_output_path(require_param(params, "path", str))
    if not path.exists():
        raise ValidationError("FILE_NOT_FOUND", "Data source was not found.", {"path": str(path)})
    return {
        "path": str(path),
        "exists": True,
        "is_file": path.is_file(),
        "suffix": path.suffix.lower(),
        "size": path.stat().st_size if path.is_file() else None,
        "supported_as_vector": path.suffix.lower() in {".shp", ".gpkg", ".geojson", ".json", ".kml", ".gpx"},
        "supported_as_raster": path.suffix.lower() in {".tif", ".tiff", ".vrt", ".asc", ".img", ".jp2"},
    }


def broken_data_source_report(params: dict[str, Any], context: dict[str, Any]):
    broken = []
    for layer in project().mapLayers().values():
        if not layer.isValid():
            broken.append({"layer_id": layer.id(), "name": layer.name(), "source": layer.source(), "type": layer_type_name(layer)})
    return {"broken_count": len(broken), "broken_layers": broken}


def repair_data_source_path(params: dict[str, Any], context: dict[str, Any]):
    if not context.get("dry_run"):
        raise ValidationError("REPAIR_DATA_SOURCE_NOT_ENABLED", "Data source path repair is planned and currently dry-run only.", {})
    return {"dry_run": True, "layer_id": params.get("layer_id"), "new_path": params.get("new_path"), "changes": ["Would update layer source path after validation."]}


def validate_service_url(params: dict[str, Any], context: dict[str, Any]):
    url = require_param(params, "url", str)
    return {"url": url, "safe_parts": _safe_url(url), "network_request_made": False}


def inspect_ogc_service(params: dict[str, Any], context: dict[str, Any]):
    payload = validate_service_url(params, context)
    payload["service_type"] = str(params.get("service_type", "unknown")).upper()
    payload["note"] = "Network probing is disabled by default; this is a local URL safety inspection."
    return payload


def test_service_connection(params: dict[str, Any], context: dict[str, Any]):
    if not bool(params.get("confirm_network")):
        raise ValidationError("NETWORK_CONFIRMATION_REQUIRED", "Network service tests require confirm_network=true.", {})
    return {"network_test": "planned", "url": require_param(params, "url", str)}


def list_ogc_connections(params: dict[str, Any], context: dict[str, Any]):
    return {"connections": [], "note": "QGIS stored OGC connection inventory is planned; no credentials are exposed."}


def load_wms_layer(params: dict[str, Any], context: dict[str, Any]):
    return _network_load_blocked(params, context, "WMS")


def load_wfs_layer(params: dict[str, Any], context: dict[str, Any]):
    return _network_load_blocked(params, context, "WFS")


def load_xyz_tile_layer(params: dict[str, Any], context: dict[str, Any]):
    return _network_load_blocked(params, context, "XYZ")


def load_arcgis_rest_layer(params: dict[str, Any], context: dict[str, Any]):
    return _network_load_blocked(params, context, "ArcGIS REST")


def _network_load_blocked(params: dict[str, Any], context: dict[str, Any], service_type: str):
    validate_service_url(params, context)
    if context.get("dry_run"):
        return {"dry_run": True, "service_type": service_type, "network_request_made": False}
    raise ValidationError("NETWORK_LOAD_NOT_ENABLED", f"{service_type} loading requires an explicit future network-enabled workflow.", {"service_type": service_type})


def load_gpx(params: dict[str, Any], context: dict[str, Any]):
    path = normalize_output_path(require_param(params, "path", str))
    if path.suffix.lower() != ".gpx":
        raise ValidationError("BAD_REQUEST", "load_gpx requires a .gpx file.", {"suffix": path.suffix})
    return load_vector_layer({"path": str(path), "name": params.get("name") or path.stem}, context)


def list_gpx_layers(params: dict[str, Any], context: dict[str, Any]):
    layers = [layer for layer in project().mapLayers().values() if layer.source().lower().endswith(".gpx") or ".gpx|" in layer.source().lower()]
    return {"layers": [{"layer_id": layer.id(), "name": layer.name(), "source": layer.source(), "crs": crs_authid(layer.crs()), "extent": extent_to_dict(layer)} for layer in layers], "count": len(layers)}


def summarize_gpx_track(params: dict[str, Any], context: dict[str, Any]):
    path_value = params.get("path")
    if path_value:
        path = normalize_output_path(str(path_value))
        if not path.exists():
            raise ValidationError("FILE_NOT_FOUND", "GPX file was not found.", {"path": str(path)})
        try:
            root = _safe_xml_root_from_file(path)
            ns = {"gpx": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            trk = root.findall(".//gpx:trk", ns) if ns else root.findall(".//trk")
            trkpt = root.findall(".//gpx:trkpt", ns) if ns else root.findall(".//trkpt")
            wpt = root.findall(".//gpx:wpt", ns) if ns else root.findall(".//wpt")
            return {"path": str(path), "track_count": len(trk), "track_point_count": len(trkpt), "waypoint_count": len(wpt)}
        except ET.ParseError as exc:
            raise ValidationError("BAD_GPX", "GPX XML could not be parsed.", {"error": str(exc)}) from exc
    layer_id = require_param(params, "layer_id", str)
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    return {"layer_id": layer.id(), "name": layer.name(), "feature_count": layer.featureCount(), "crs": crs_authid(layer.crs()), "extent": extent_to_dict(layer)}


def gpx_track_length(params: dict[str, Any], context: dict[str, Any]):
    summary = summarize_gpx_track(params, context)
    summary["length_calculation"] = "planned"
    summary["note"] = "Metric GPX length calculation requires CRS/geodesic strategy validation."
    return summary


def gpx_track_extent(params: dict[str, Any], context: dict[str, Any]):
    return summarize_gpx_track(params, context)


def gpx_to_layer(params: dict[str, Any], context: dict[str, Any]):
    return load_gpx(params, context)


def map_gpx_track(params: dict[str, Any], context: dict[str, Any]):
    if context.get("dry_run"):
        return {"dry_run": True, "steps": ["load_gpx", "generate_professional_map"]}
    return load_gpx(params, context)


def list_database_connections(params: dict[str, Any], context: dict[str, Any]):
    return {"connections": [], "note": "Database connection inventory is planned; credentials are never exposed."}


def inspect_database_connection(params: dict[str, Any], context: dict[str, Any]):
    name = require_param(params, "name", str)
    return {"name": name, "status": "not_configured_or_not_exposed", "credentials_exposed": False}


def test_postgis_connection(params: dict[str, Any], context: dict[str, Any]):
    raise ValidationError("DATABASE_CONNECTION_NOT_ENABLED", "PostGIS connection tests are disabled until credential-safe connection handling is implemented.", {})


def list_postgis_tables(params: dict[str, Any], context: dict[str, Any]):
    raise ValidationError("DATABASE_CONNECTION_NOT_ENABLED", "PostGIS table listing is disabled until credential-safe connection handling is implemented.", {})


def load_postgis_layer(params: dict[str, Any], context: dict[str, Any]):
    raise ValidationError("DATABASE_LOAD_NOT_ENABLED", "PostGIS layer loading is disabled until credential-safe connection handling is implemented.", {})


def inspect_postgis_layer(params: dict[str, Any], context: dict[str, Any]):
    return inspect_database_connection(params, context)
