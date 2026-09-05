from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
import xml.etree.ElementTree as ET

from ..security import normalize_output_path
from ..validators import ValidationError, require_param
from .cartography_engine import compose_map
from .common import crs_authid, extent_to_dict, layer_type_name, project
from .load_layers import handle as load_vector_layer
from .project_overview import redact_layer_source, redact_source

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
            # Uma camada quebrada de banco (PostGIS/MSSQL/Oracle) ainda carrega
            # a senha na string de conexão mesmo inválida — redigir aqui.
            broken.append({"layer_id": layer.id(), "name": layer.name(), "source": redact_layer_source(layer), "type": layer_type_name(layer)})
    return {"broken_count": len(broken), "broken_layers": broken}


def repair_data_source_path(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    new_path = normalize_output_path(require_param(params, "new_path", str))
    if not new_path.exists():
        raise ValidationError("FILE_NOT_FOUND", "The replacement data source path was not found.", {"path": str(new_path)})
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    provider = str(params.get("provider") or layer.providerType() or "ogr")
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "layer_id": layer_id,
            "new_path": str(new_path),
            "provider": provider,
            "changes": ["Would call layer.setDataSource() with the new path and re-check layer validity."],
        }
    layer.setDataSource(str(new_path), layer.name(), provider)
    if not layer.isValid():
        raise ValidationError(
            "REPAIR_FAILED",
            "QGIS could not open the new data source; the layer stayed broken. Check the path, the "
            "provider and that the new file actually holds compatible data.",
            {"layer_id": layer_id, "path": str(new_path), "provider": provider, "error": _safe_layer_error_text(layer)[:400]},
        )
    return {
        "layer_id": layer.id(),
        "name": layer.name(),
        "new_path": str(new_path),
        "provider": provider,
        "valid": True,
    }


def validate_service_url(params: dict[str, Any], context: dict[str, Any]):
    url = require_param(params, "url", str)
    return {"url": url, "safe_parts": _safe_url(url), "network_request_made": False}


def inspect_ogc_service(params: dict[str, Any], context: dict[str, Any]):
    payload = validate_service_url(params, context)
    payload["service_type"] = str(params.get("service_type", "unknown")).upper()
    payload["note"] = "Network probing is disabled by default; this is a local URL safety inspection."
    return payload


def test_service_connection(params: dict[str, Any], context: dict[str, Any]):
    url = require_param(params, "url", str)
    _safe_url(url)
    if not bool(params.get("confirm_network")):
        raise ValidationError("NETWORK_CONFIRMATION_REQUIRED", "Network service tests require confirm_network=true.", {})
    service_type = str(params.get("service_type", "")).strip().upper()
    timeout_seconds = float(params.get("timeout_seconds", 5.0))
    if not 0 < timeout_seconds <= 30:
        raise ValidationError("BAD_REQUEST", "timeout_seconds must be between 0 (exclusive) and 30.", {"timeout_seconds": timeout_seconds})
    if service_type in {"WMS", "WFS"}:
        separator = "&" if "?" in url else "?"
        request_url = f"{url}{separator}SERVICE={service_type}&REQUEST=GetCapabilities"
        method = "GET"
    else:
        request_url = url
        method = "HEAD"
    request = urllib.request.Request(request_url, method=method, headers={"User-Agent": "SIGMAI/1.0"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = int(getattr(response, "status", None) or response.getcode())
        return {
            "url": redact_source(url),
            "service_type": service_type or "generic",
            "method": method,
            "reachable": True,
            "status_code": status_code,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    except urllib.error.HTTPError as exc:
        # O servidor respondeu — ele existe e está no ar — só recusou o
        # método/caminho pedido. Isso é uma conexão bem-sucedida do ponto de
        # vista de "o serviço está acessível", mesmo que o corpo seja um erro.
        return {
            "url": redact_source(url),
            "service_type": service_type or "generic",
            "method": method,
            "reachable": True,
            "status_code": exc.code,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "note": "O servidor respondeu com um status de erro HTTP; o serviço existe mas rejeitou esta requisição.",
        }
    except Exception as exc:
        raise ValidationError(
            "NETWORK_TEST_FAILED",
            f"Não foi possível alcançar o serviço: {exc}",
            {"url": redact_source(url), "method": method, "service_type": service_type or "generic"},
        ) from exc


def list_ogc_connections(params: dict[str, Any], context: dict[str, Any]):
    from qgis.core import QgsSettings  # type: ignore

    settings = QgsSettings()
    connections: list[dict[str, Any]] = []
    for service_type, group in (
        ("WMS", "qgis/connections-wms"),
        ("WFS", "qgis/connections-wfs"),
        ("XYZ", "qgis/connections-xyz"),
    ):
        settings.beginGroup(group)
        try:
            for name in settings.childGroups():
                url = settings.value(f"{name}/url", "")
                connections.append({"service_type": service_type, "name": name, "url": str(url) if url else ""})
        finally:
            settings.endGroup()
    return {"connections": connections, "count": len(connections), "note": "Credentials are never read or exposed here."}


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


#: Tipos de serviço cuja camada QGIS não faz NENHUMA checagem síncrona de
#: conectividade ao ser construída: isValid() volta True mesmo para uma URL
#: completamente falsa — a checagem real só acontece depois, quando o QGIS
#: efetivamente busca um tile ou uma imagem para desenhar. Provado por
#: reprodução real com https://example.test/... : XYZ e ArcGIS REST voltam
#: valid=true; WMS e WFS fazem GetCapabilities/GetFeature síncrono e
#: detectam a falha aqui (WFS, aliás, é o provedor do defeito de segfault
#: logo abaixo — os dois defeitos nascem da mesma causa: nem todo provedor
#: se comporta como WMS).
_NO_SYNC_CONNECTIVITY_CHECK = {"XYZ", "ArcGIS REST"}


def _safe_layer_error_text(layer: Any) -> str:
    """Texto de erro da camada, sem chamar ``QgsError.summary()``.

    ``summary()`` crasha nativamente (segfault, não exceção Python) quando o
    ``QgsError`` do provedor WFS está vazio — reproduzido 2/2 vezes contra um
    servidor WFS inalcançável. ``isEmpty()`` e ``message()`` são seguros nos
    mesmos cenários (inclusive quando vazios) e foram checados também contra
    resposta 404, corpo não-XML e ServiceExceptionReport: em todos, o
    provedor WFS não populava nada em ``layer.error()`` mesmo — ou seja,
    ``summary()`` nunca tinha conteúdo útil a mais para dar aqui, só o risco
    de derrubar o processo. WMS, com erro de fato populado, usa ``message()``
    igual e continua informativo.
    """
    try:
        error = layer.error()
    except Exception:
        return ""
    try:
        if error is None or error.isEmpty():
            return ""
        return str(error.message() or "")
    except Exception:
        return ""


def _finish_network_layer(layer: Any, name: str, service_type: str, url: str,
                          attribution: str, extra: dict[str, Any] | None = None):
    """Valida, credita e entrega a camada ao projeto.

    Uma camada inválida NÃO entra no projeto quando o provedor consegue
    detectar isso de forma síncrona (WMS, WFS): antes o assistente recebia
    sucesso e o usuário via uma entrada morta na árvore de camadas, sem saber
    se o problema era a URL, o nome da camada ou a falta de rede.

    Para XYZ e ArcGIS REST essa checagem simplesmente não existe no provedor
    — ``isValid()`` volta True mesmo para uma URL inventada, porque a camada
    só busca dado de verdade quando o mapa desenha. Aqui isso é explícito na
    resposta (``connectivity_confirmed=False`` e uma nota) em vez de deixar a
    IA supor que ``valid: true`` significa "servidor confirmado no ar" — o
    que só é verdade para WMS e WFS.
    """
    if not layer.isValid():
        raise ValidationError(
            f"{service_type}_LAYER_INVALID",
            f"O QGIS não conseguiu abrir esta fonte {service_type}. As causas usuais são, nesta "
            "ordem: o servidor não respondeu (sem rede, ou fora do ar), o nome da camada não "
            "existe nesse serviço, ou o CRS pedido não é oferecido por ele. Confira com "
            "inspect_ogc_service antes de repetir.",
            {"url": redact_source(url), "service_type": service_type, "error": _safe_layer_error_text(layer)[:400]},
        )
    try:
        layer.setAttribution(attribution)
    except Exception:
        pass
    project().addMapLayer(layer)
    connectivity_confirmed = service_type not in _NO_SYNC_CONNECTIVITY_CHECK
    payload = {
        "layer_id": layer.id(),
        "name": layer.name(),
        "service_type": service_type,
        "url": redact_source(url),
        "attribution": attribution,
        "source_kind": _tile_source_kind(url),
        "crs": crs_authid(layer.crs()),
        "valid": True,
        "connectivity_confirmed": connectivity_confirmed,
    }
    if not connectivity_confirmed:
        alvo = "o servidor" if _tile_source_kind(url) == "rede" else "os arquivos de tile no disco"
        payload["note"] = (
            f"O provedor {service_type} não faz checagem síncrona de conectividade: valid=true "
            f"aqui só confirma que o QGIS aceitou a estrutura da fonte, não que {alvo} responde de "
            "fato. Um erro só aparece mais tarde, ao desenhar o mapa."
        )
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
        return {"dry_run": True, "service_type": "XYZ", "url": redact_source(url), "name": name,
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
        return {"dry_run": True, "service_type": "WMS", "url": redact_source(url), "layers": camadas,
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
        return {"dry_run": True, "service_type": "WFS", "url": redact_source(url), "typename": typename,
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
        return {"dry_run": True, "service_type": "ArcGIS REST", "url": redact_source(url), "name": name,
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
    # A filtragem usa layer.source() cru (GPX nunca carrega credencial); só a
    # saída devolvida à IA passa por redact_layer_source.
    layers = [layer for layer in project().mapLayers().values() if layer.source().lower().endswith(".gpx") or ".gpx|" in layer.source().lower()]
    return {"layers": [{"layer_id": layer.id(), "name": layer.name(), "source": redact_layer_source(layer), "crs": crs_authid(layer.crs()), "extent": extent_to_dict(layer)} for layer in layers], "count": len(layers)}


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


def _distance_area(source_crs: Any) -> Any:
    from qgis.core import QgsDistanceArea  # type: ignore

    distance_area = QgsDistanceArea()
    distance_area.setEllipsoid("WGS84")
    distance_area.setSourceCrs(source_crs, project().transformContext())
    return distance_area


def _measure_track_geometries(features: Any, source_crs: Any) -> tuple[float, int, int]:
    """Comprimento elipsoidal total (m), contagem de trechos e de feições.

    "Trecho" é cada parte da geometria (``QgsGeometry.constGet().partCount()``)
    — no driver GPX do GDAL, cada ``<trkseg>`` de um ``<trk>`` vira uma parte
    do MultiLineString daquela feição, então somar partes através das feições
    dá a contagem real de segmentos de trilha, não só de feições ``<trk>``.
    """
    distance_area = _distance_area(source_crs)
    total_length_m = 0.0
    segment_count = 0
    feature_count = 0
    for feature in features:
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        feature_count += 1
        total_length_m += distance_area.measureLength(geometry)
        native = geometry.constGet()
        segment_count += native.partCount() if hasattr(native, "partCount") else 1
    return total_length_m, segment_count, feature_count


def gpx_track_length(params: dict[str, Any], context: dict[str, Any]):
    path_value = params.get("path")
    if path_value:
        path = normalize_output_path(str(path_value))
        if not path.exists():
            raise ValidationError("FILE_NOT_FOUND", "GPX file was not found.", {"path": str(path)})
        from qgis.core import QgsVectorLayer  # type: ignore

        tracks_layer = QgsVectorLayer(f"{path}|layername=tracks", "sigmai_gpx_tracks", "ogr")
        if not tracks_layer.isValid():
            raise ValidationError("BAD_GPX", "QGIS could not read the tracks layer from this GPX file.", {"path": str(path)})
        total_length_m, segment_count, feature_count = _measure_track_geometries(tracks_layer.getFeatures(), tracks_layer.crs())
        return {
            "path": str(path),
            "length_meters": round(total_length_m, 2),
            "segment_count": segment_count,
            "track_feature_count": feature_count,
            "crs": crs_authid(tracks_layer.crs()),
            "method": "QgsDistanceArea, ellipsoidal WGS84",
        }
    layer_id = require_param(params, "layer_id", str)
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "gpx_track_length requires a vector layer.", {"layer_id": layer_id})
    total_length_m, segment_count, feature_count = _measure_track_geometries(layer.getFeatures(), layer.crs())
    return {
        "layer_id": layer.id(),
        "name": layer.name(),
        "length_meters": round(total_length_m, 2),
        "segment_count": segment_count,
        "track_feature_count": feature_count,
        "crs": crs_authid(layer.crs()),
        "method": "QgsDistanceArea, ellipsoidal WGS84",
    }


def gpx_track_extent(params: dict[str, Any], context: dict[str, Any]):
    return summarize_gpx_track(params, context)


def gpx_to_layer(params: dict[str, Any], context: dict[str, Any]):
    return load_gpx(params, context)


def _load_gpx_track_layer(path: Path, name: str):
    """Carrega especificamente o sublayer "tracks" do driver GPX do GDAL.

    ``load_gpx``/``load_vector_layer`` abrem o arquivo sem indicar sublayer,
    o que faz o GDAL escolher "waypoints" por padrão — vazio (0 feições) para
    um GPX que só tem trilha, como os do autor. map_gpx_track existe para
    mapear a TRILHA; carregar o sublayer errado produziria um mapa "de
    sucesso" com o quadro vazio, o mesmo defeito de fundo que esta rodada
    inteira corrige, só que disfarçado de arquivo exportado com tamanho > 0.
    """
    from qgis.core import QgsVectorLayer  # type: ignore

    layer = QgsVectorLayer(f"{path}|layername=tracks", name, "ogr")
    if not layer.isValid() or layer.featureCount() == 0:
        raise ValidationError(
            "GPX_HAS_NO_TRACK",
            "This GPX file has no usable <trk> track data to map (only waypoints/routes, or an "
            "empty track). map_gpx_track needs an actual track; use load_gpx/gpx_to_layer for "
            "waypoint-only files instead.",
            {"path": str(path)},
        )
    project().addMapLayer(layer)
    return layer


def map_gpx_track(params: dict[str, Any], context: dict[str, Any]):
    """Carrega a trilha de um GPX e a compõe num mapa — o caso de uso das
    coletas de campo do próprio autor. Antes só carregava a camada e nunca
    chamava o segundo passo que anunciava; agora ``compose_map`` roda de
    verdade sobre a camada de trilha carregada, e o resultado devolvido é o
    da composição (não um "sucesso" da simples carga do GPX)."""
    path = normalize_output_path(require_param(params, "path", str))
    if path.suffix.lower() != ".gpx":
        raise ValidationError("BAD_REQUEST", "map_gpx_track requires a .gpx file.", {"suffix": path.suffix})
    if not path.exists():
        raise ValidationError("FILE_NOT_FOUND", "GPX file was not found.", {"path": str(path)})
    name = str(params.get("name") or path.stem)
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "steps": ["load_gpx", "compose_map"],
            "path": str(path),
            "name": name,
            "changes": ["Would load the GPX track layer and compose a map from it, without modifying the source file."],
        }
    layer = _load_gpx_track_layer(path, name)
    compose_params = {key: value for key, value in params.items() if key not in {"path", "name"}}
    compose_params["layer_ids"] = [layer.id()]
    if not str(compose_params.get("title", "")).strip():
        compose_params["title"] = f"Trilha {name}".strip()
    map_result = compose_map(compose_params, context)
    return {"layer_id": layer.id(), "layer_name": layer.name(), "feature_count": layer.featureCount(), "map": map_result}


def list_database_connections(params: dict[str, Any], context: dict[str, Any]):
    from qgis.core import QgsSettings  # type: ignore

    settings = QgsSettings()
    connections: list[dict[str, Any]] = []
    settings.beginGroup("PostgreSQL/connections")
    try:
        for name in settings.childGroups():
            connections.append(
                {
                    "name": name,
                    "host": str(settings.value(f"{name}/host", "")),
                    "port": str(settings.value(f"{name}/port", "")),
                    "database": str(settings.value(f"{name}/database", "")),
                    "username": str(settings.value(f"{name}/username", "")),
                }
            )
    finally:
        settings.endGroup()
    return {"connections": connections, "count": len(connections), "note": "Passwords and authcfg are never read or exposed here."}


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
