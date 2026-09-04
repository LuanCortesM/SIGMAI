from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
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


#: Atribuição obrigatória de fontes de tiles conhecidas. Um mapa de base é
#: dado de terceiro sob licença: publicar a imagem sem o crédito viola a
#: licença e, na prática, torna o mapa não citável — o mesmo motivo pelo qual a
#: regra CART007 exige fonte declarada.
KNOWN_TILE_ATTRIBUTION: dict[str, str] = {
    "tile.openstreetmap.org": "© OpenStreetMap contributors (ODbL)",
    "a.tile.openstreetmap.org": "© OpenStreetMap contributors (ODbL)",
    "b.tile.openstreetmap.org": "© OpenStreetMap contributors (ODbL)",
    "c.tile.openstreetmap.org": "© OpenStreetMap contributors (ODbL)",
    "tile.opentopomap.org": "© OpenTopoMap, © OpenStreetMap contributors (CC-BY-SA)",
}

#: Um XYZ pode apontar para um cache local — o caso de campo, sem sinal. Ler
#: tile do disco não é acesso de rede e não exige confirm_network.
_LOCAL_TILE_SCHEMES = {"file"}


def _tile_source_kind(url: str) -> str:
    scheme = urlparse(url.replace("{z}", "0").replace("{x}", "0").replace("{y}", "0")).scheme
    return "local" if scheme in _LOCAL_TILE_SCHEMES else "rede"


def _resolve_attribution(params: dict[str, Any], url: str, service_type: str) -> str:
    """A atribuição é obrigatória e não é adivinhada quando não se conhece a fonte."""
    declarada = str(params.get("attribution", "")).strip()
    if declarada:
        return declarada
    host = (urlparse(url).hostname or "").lower()
    conhecida = KNOWN_TILE_ATTRIBUTION.get(host)
    if conhecida:
        return conhecida
    if _tile_source_kind(url) == "local":
        return str(params.get("attribution", "")).strip() or "Fonte local (sem atribuição declarada)"
    raise ValidationError(
        "ATTRIBUTION_REQUIRED",
        f"Informe attribution para esta fonte {service_type}: o mapa de base é dado de terceiro "
        "sob licença, e publicar a imagem sem o crédito viola a licença e deixa o mapa sem "
        "procedência. Ex.: attribution=\"© OpenStreetMap contributors (ODbL)\".",
        {"host": host, "service_type": service_type},
    )


def _require_network_ok(params: dict[str, Any], url: str, service_type: str) -> None:
    if _tile_source_kind(url) == "local":
        return
    if not bool(params.get("confirm_network")):
        raise ValidationError(
            "NETWORK_CONFIRMATION_REQUIRED",
            f"Carregar {service_type} busca dados num servidor externo. Repita com "
            "confirm_network=true para autorizar essa saída de rede.",
            {"service_type": service_type, "url_host": urlparse(url).hostname or ""},
        )


def _finish_network_layer(layer: Any, name: str, service_type: str, url: str,
                          attribution: str, extra: dict[str, Any] | None = None):
    """Valida, credita e entrega a camada ao projeto.

    Uma camada inválida NÃO entra no projeto: antes o assistente recebia
    sucesso e o usuário via uma entrada morta na árvore de camadas, sem saber
    se o problema era a URL, o nome da camada ou a falta de rede.
    """
    if not layer.isValid():
        raise ValidationError(
            f"{service_type}_LAYER_INVALID",
            f"O QGIS não conseguiu abrir esta fonte {service_type}. As causas usuais são, nesta "
            "ordem: o servidor não respondeu (sem rede, ou fora do ar), o nome da camada não "
            "existe nesse serviço, ou o CRS pedido não é oferecido por ele. Confira com "
            "inspect_ogc_service antes de repetir.",
            {"url": url, "service_type": service_type, "error": str(layer.error().summary() or "")[:400]},
        )
    try:
        layer.setAttribution(attribution)
    except Exception:
        pass
    project().addMapLayer(layer)
    payload = {
        "layer_id": layer.id(),
        "name": layer.name(),
        "service_type": service_type,
        "url": url,
        "attribution": attribution,
        "source_kind": _tile_source_kind(url),
        "crs": crs_authid(layer.crs()),
        "valid": True,
    }
    payload.update(extra or {})
    return payload


def load_xyz_tile_layer(params: dict[str, Any], context: dict[str, Any]):
    """Mapa de base de tiles XYZ — o elemento que dá contexto visual ao mapa.

    Aceita qualquer template ``{z}/{x}/{y}``, inclusive ``file://`` apontando
    para um cache de tiles no disco, que é o caso de campo sem sinal.
    """
    from qgis.core import QgsRasterLayer  # type: ignore

    url = require_param(params, "url", str)
    name = str(params.get("name", "") or "Mapa de base")
    if "{z}" not in url or "{x}" not in url or "{y}" not in url:
        raise ValidationError(
            "BAD_REQUEST",
            "Um endereço XYZ precisa dos três marcadores {z}, {x} e {y} — por exemplo "
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png.",
            {"url": url},
        )
    if _tile_source_kind(url) == "rede":
        _safe_url(url.replace("{z}", "0").replace("{x}", "0").replace("{y}", "0"))
    attribution = _resolve_attribution(params, url, "XYZ")
    _require_network_ok(params, url, "XYZ")

    zoom_min = int(params.get("zoom_min", 0))
    zoom_max = int(params.get("zoom_max", 19))
    if not 0 <= zoom_min <= zoom_max <= 25:
        raise ValidationError(
            "BAD_REQUEST",
            "Os níveis de zoom precisam obedecer 0 <= zoom_min <= zoom_max <= 25.",
            {"zoom_min": zoom_min, "zoom_max": zoom_max},
        )

    if context.get("dry_run"):
        return {"dry_run": True, "service_type": "XYZ", "url": url, "name": name,
                "attribution": attribution, "network_request_made": False}

    uri = f"type=xyz&url={quote(url, safe='')}&zmin={zoom_min}&zmax={zoom_max}"
    layer = QgsRasterLayer(uri, name, "wms")
    return _finish_network_layer(layer, name, "XYZ", url, attribution,
                                 {"zoom_min": zoom_min, "zoom_max": zoom_max})


def load_wms_layer(params: dict[str, Any], context: dict[str, Any]):
    """Camada WMS — o formato em que órgãos públicos publicam mapa pronto."""
    from qgis.core import QgsRasterLayer  # type: ignore

    url = require_param(params, "url", str)
    _safe_url(url)
    camadas = params.get("layers")
    if isinstance(camadas, str):
        camadas = [camadas]
    if not camadas or not all(isinstance(item, str) and item.strip() for item in camadas):
        raise ValidationError(
            "BAD_REQUEST",
            "Informe layers com o nome de ao menos uma camada do serviço WMS. "
            "inspect_ogc_service lista os nomes oferecidos pelo servidor.",
            {"received": camadas},
        )
    name = str(params.get("name", "") or camadas[0])
    crs = str(params.get("crs", "EPSG:4326"))
    image_format = str(params.get("format", "image/png"))
    attribution = _resolve_attribution(params, url, "WMS")
    _require_network_ok(params, url, "WMS")

    if context.get("dry_run"):
        return {"dry_run": True, "service_type": "WMS", "url": url, "layers": camadas,
                "name": name, "attribution": attribution, "network_request_made": False}

    uri = "&".join([
        f"crs={quote(crs, safe='')}",
        f"format={quote(image_format, safe='')}",
        "layers=" + "&layers=".join(quote(item, safe="") for item in camadas),
        "styles=",
        f"url={quote(url, safe='')}",
    ])
    layer = QgsRasterLayer(uri, name, "wms")
    return _finish_network_layer(layer, name, "WMS", url, attribution, {"layers": camadas, "crs_requested": crs})


def load_wfs_layer(params: dict[str, Any], context: dict[str, Any]):
    """Camada WFS — feições vetoriais servidas pela rede, com geometria real."""
    from qgis.core import QgsVectorLayer  # type: ignore

    url = require_param(params, "url", str)
    _safe_url(url)
    typename = str(params.get("typename", "") or params.get("layer", "")).strip()
    if not typename:
        raise ValidationError(
            "BAD_REQUEST",
            "Informe typename com o nome do tipo de feição do serviço WFS "
            "(inspect_ogc_service lista os disponíveis).",
            {},
        )
    name = str(params.get("name", "") or typename)
    crs = str(params.get("crs", "EPSG:4326"))
    attribution = _resolve_attribution(params, url, "WFS")
    _require_network_ok(params, url, "WFS")

    if context.get("dry_run"):
        return {"dry_run": True, "service_type": "WFS", "url": url, "typename": typename,
                "name": name, "attribution": attribution, "network_request_made": False}

    uri = (
        f"{url}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typename={quote(typename, safe='')}&srsname={quote(crs, safe='')}"
    )
    layer = QgsVectorLayer(uri, name, "WFS")
    return _finish_network_layer(layer, name, "WFS", url, attribution, {"typename": typename})


def load_arcgis_rest_layer(params: dict[str, Any], context: dict[str, Any]):
    """Serviço ArcGIS REST — comum em prefeituras e órgãos estaduais."""
    from qgis.core import QgsRasterLayer  # type: ignore

    url = require_param(params, "url", str)
    _safe_url(url)
    name = str(params.get("name", "") or "ArcGIS REST")
    crs = str(params.get("crs", "EPSG:4326"))
    attribution = _resolve_attribution(params, url, "ArcGIS REST")
    _require_network_ok(params, url, "ArcGIS REST")

    if context.get("dry_run"):
        return {"dry_run": True, "service_type": "ArcGIS REST", "url": url, "name": name,
                "attribution": attribution, "network_request_made": False}

    uri = f"crs={quote(crs, safe='')}&format=png&layer=0&url={quote(url, safe='')}"
    layer = QgsRasterLayer(uri, name, "arcgismapserver")
    return _finish_network_layer(layer, name, "ArcGIS REST", url, attribution, {"crs_requested": crs})


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
