"""Panorama do projeto numa única chamada.

Um agente de IA que precisa de projeto, CRS, camadas, campos e extensões gasta
quatro ou cinco viagens de ida e volta para montar esse quadro, e cada viagem
passa pela fila do QGIS. Consolidar reduz a latência percebida e, mais
importante, elimina a janela em que o agente decide com informação parcial —
que é de onde saem os ids de camada inventados.
"""

from __future__ import annotations

from typing import Any

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


def _short_source(layer) -> str:
    try:
        source = str(layer.source())
    except Exception:
        return ""
    # Fontes de PostGIS e serviços carregam senha e chaves de API na URI.
    for marker in ("password=", "key=", "token=", "apikey="):
        index = source.lower().find(marker)
        if index >= 0:
            return source[:index] + "<omitido>"
    return source[:400]
