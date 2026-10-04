"""Panorama do projeto numa única chamada.

Um agente de IA que precisa de projeto, CRS, camadas, campos e extensões gasta
quatro ou cinco viagens de ida e volta para montar esse quadro, e cada viagem
passa pela fila do QGIS. Consolidar reduz a latência percebida e, mais
importante, elimina a janela em que o agente decide com informação parcial —
que é de onde saem os ids de camada inventados.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote

from .common import crs_authid, extent_to_dict, layer_type_name, project


def handle(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    include_fields = bool(params.get("include_fields", True))
    qgs_project = project()
    layers: list[dict[str, Any]] = []

    try:
        tree_order = [node.layerId() for node in qgs_project.layerTreeRoot().findLayers()]
    except Exception:
        tree_order = []

    for layer in qgs_project.mapLayers().values():
        entry: dict[str, Any] = {
            "id": layer.id(),
            "name": layer.name(),
            "type": layer_type_name(layer),
            "crs": crs_authid(layer.crs()),
            "crs_description": _safe(layer.crs().description),
            "crs_is_geographic": _safe(layer.crs().isGeographic),
            "valid": bool(_safe(layer.isValid, False)),
            "source": _short_source(layer),
        }
        try:
            entry["extent"] = extent_to_dict(layer)
        except Exception:
            entry["extent"] = None
        if hasattr(layer, "featureCount"):
            try:
                entry["feature_count"] = int(layer.featureCount())
            except Exception:
                pass
        if hasattr(layer, "geometryType"):
            entry["geometry"] = _geometry_name(layer)
        if include_fields and hasattr(layer, "fields"):
            try:
                entry["fields"] = [
                    {"name": field.name(), "type": field.typeName()} for field in layer.fields()
                ]
            except Exception:
                entry["fields"] = []
        if hasattr(layer, "renderer"):
            try:
                entry["renderer"] = type(layer.renderer()).__name__
            except Exception:
                pass
        try:
            entry["visible"] = bool(qgs_project.layerTreeRoot().findLayer(layer.id()).isVisible())
        except Exception:
            entry["visible"] = None
        entry["draw_order_index"] = tree_order.index(layer.id()) if layer.id() in tree_order else None
        layers.append(entry)

    layers.sort(key=lambda item: (item["draw_order_index"] is None, item["draw_order_index"] or 0))

    layouts = []
    try:
        for layout in qgs_project.layoutManager().layouts():
            layouts.append({"name": layout.name(), "item_count": len(list(layout.items()))})
    except Exception:
        pass

    return {
        "project_path": _safe(qgs_project.fileName, "") or "",
        "project_title": _safe(qgs_project.title, "") or "",
        "project_crs": crs_authid(qgs_project.crs()),
        "project_crs_description": _safe(qgs_project.crs().description),
        "project_crs_is_geographic": _safe(qgs_project.crs().isGeographic),
        "layer_count": len(layers),
        "layers": layers,
        "layouts": layouts,
        "hint": (
            "Use o campo 'id' de cada camada nos comandos. A ordem da lista é a ordem de desenho "
            "(o primeiro item fica embaixo). Camadas com valid=false não renderizam."
        ),
    }


def _safe(callable_obj, default=None):
    try:
        return callable_obj()
    except Exception:
        return default


def _geometry_name(layer) -> str:
    try:
        from qgis.core import Qgis, QgsWkbTypes  # type: ignore

        from ..cartography.qtcompat import geometry_type

        value = layer.geometryType()
        for name in ("Point", "Line", "Polygon"):
            try:
                if value == geometry_type(Qgis, QgsWkbTypes, name):
                    return name
            except Exception:
                continue
    except Exception:
        pass
    return "unknown"


#: Chaves de credencial reconhecidas em URI de camada. Cobre string de
#: conexão de banco (PostGIS/MSSQL/Oracle, que usam ``QgsDataSourceUri`` e
#: escrevem ``chave='valor'`` ou ``chave=valor`` separado por espaço, e
#: também ODBC ``chave=valor;``) e chave de API de serviço. Deliberadamente
#: NÃO inclui ``key=`` sozinho: em URI PostGIS/MSSQL, ``key='id'`` é o nome
#: da coluna de chave primária, não segredo — redigir isso não protege nada
#: e estraga a leitura à toa. Como parâmetro de query de URL (``?key=...``),
#: "key" É um padrão real de chave de API (ex.: MapTiler), e esse caso é
#: tratado à parte por ``_URL_QUERY_KEY_RE`` abaixo, só quando prefixado por
#: ``?`` ou ``&``.
_CREDENTIAL_KEYS = (
    "password", "pwd", "apikey", "api_key", "api-key",
    "secret_key", "secret", "access_key", "access_token",
    "client_secret", "token",
)

#: Valor de uma credencial: entre aspas simples/duplas (formato QGIS
#: ``QgsDataSourceUri``, ex. ``password='...'``) ou sem aspas até o
#: próximo separador (``&``, ``;``, espaço — formato ODBC/URL).
_VALUE_PATTERN = r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|[^&;\s'\"]*"

_CREDENTIAL_RE = re.compile(
    r"(?i)\b(" + "|".join(_CREDENTIAL_KEYS) + r")\s*=\s*(" + _VALUE_PATTERN + r")"
)
# "key=" só é credencial como parâmetro de query de URL (?key=... / &key=...).
_URL_QUERY_KEY_RE = re.compile(r"(?i)([?&]key)\s*=\s*(" + _VALUE_PATTERN + r")")
# "url=<blob percent-encoded>" aparece nas URIs que o SIGMAI monta para XYZ,
# WMS e ArcGIS REST (``quote(url, safe='')``): a URL original — key de API
# de tile incluída, se houver — fica inteira dentro do blob, sem "&"/"="
# literais (tudo virou %XX). A checagem acima não a alcança nesse formato;
# desembrulha, redige o texto decodificado e reembrulha.
_ENCODED_URL_PARAM_RE = re.compile(r"(?i)(\burl=)([^&\s]*)")


def _mask_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        quote_char = value[0]
        return f"{quote_char}<omitido>{quote_char}"
    return "<omitido>"


def _redact_key_value_pairs(text: str) -> str:
    text = _CREDENTIAL_RE.sub(lambda m: f"{m.group(1)}={_mask_value(m.group(2))}", text)
    text = _URL_QUERY_KEY_RE.sub(lambda m: f"{m.group(1)}={_mask_value(m.group(2))}", text)
    return text


def redact_source(source: str) -> str:
    """Redige credenciais numa string de fonte de camada, preservando o resto.

    Ponto único de redação usado por toda ação que devolve a fonte de uma
    camada — antes cada ação reimplementava (ou esquecia) sua própria cópia.
    Cobre string de conexão de banco (``password=``/``pwd=``, maiúsculo ou
    minúsculo, com ou sem aspas — as variações vistas em PostGIS, MSSQL e
    ODBC) e chave de API em query string de URL (``?apikey=...``,
    ``&key=...``), inclusive quando essa URL está, ela mesma,
    percent-encoded dentro de um parâmetro ``url=`` (caso das camadas de
    rede XYZ/WMS/ArcGIS REST montadas pelo SIGMAI). Um caminho de shapefile
    ou GeoPackage não bate em nenhum desses padrões e volta inalterado —
    a IA precisa do caminho para trabalhar.
    """
    if not source:
        return source

    def _fix_encoded_url(match: "re.Match[str]") -> str:
        prefix, blob = match.group(1), match.group(2)
        if not blob:
            return match.group(0)
        try:
            decoded = unquote(blob)
        except Exception:
            return match.group(0)
        redacted = _redact_key_value_pairs(decoded)
        if redacted == decoded:
            return match.group(0)
        return prefix + quote(redacted, safe="")

    redacted = _redact_key_value_pairs(source)
    redacted = _ENCODED_URL_PARAM_RE.sub(_fix_encoded_url, redacted)
    return redacted


def redact_layer_source(layer: Any) -> str:
    """``layer.source()`` com credenciais redigidas — ver ``redact_source``.

    Toda ação somente-leitura do SIGMAI que expõe a fonte de uma camada deve
    passar por aqui em vez de chamar ``layer.source()`` direto: uma camada
    PostGIS, MSSQL ou Oracle guarda a senha em texto puro na string de
    conexão, e essas ações são somente-leitura — não passam por consentimento
    algum antes de responder à IA.
    """
    try:
        source = str(layer.source())
    except Exception:
        return ""
    return redact_source(source)


def _short_source(layer) -> str:
    return redact_layer_source(layer)[:400]
