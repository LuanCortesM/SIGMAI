from __future__ import annotations

from typing import Any

from ..validators import require_param
from .gis_tools import PROCESSING_ALLOWLIST


def _registry():
    try:
        from qgis.core import QgsApplication  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc
    return QgsApplication.processingRegistry()


def list_processing_providers(params: dict[str, Any], context: dict[str, Any]):
    providers = []
    for provider in _registry().providers():
        algorithms = list(provider.algorithms())
        providers.append(
            {
                "id": provider.id(),
                "name": provider.name(),
                "active": bool(provider.isActive()),
                "algorithm_count": len(algorithms),
                "safe_algorithm_count": sum(1 for alg in algorithms if alg.id() in PROCESSING_ALLOWLIST),
            }
        )
    return {"providers": sorted(providers, key=lambda item: item["id"])}


def list_processing_algorithms(params: dict[str, Any], context: dict[str, Any]):
    provider_filter = str(params.get("provider", "")).lower()
    text_filter = str(params.get("filter", "")).lower()
    safe_only = bool(params.get("safe_only", True))
    algorithms = []
    for provider in _registry().providers():
        if provider_filter and provider.id().lower() != provider_filter:
            continue
        for alg in provider.algorithms():
            alg_id = alg.id()
            if safe_only and alg_id not in PROCESSING_ALLOWLIST:
                continue
            if text_filter and text_filter not in alg_id.lower() and text_filter not in alg.displayName().lower():
                continue
            algorithms.append(
                {
                    "id": alg_id,
                    "name": alg.displayName(),
                    "provider": provider.id(),
                    "group": alg.group(),
                    "safe": alg_id in PROCESSING_ALLOWLIST,
                }
            )
    return {"safe_only": safe_only, "algorithms": sorted(algorithms, key=lambda item: item["id"])}


def get_processing_algorithm_info(params: dict[str, Any], context: dict[str, Any]):
    alg_id = require_param(params, "algorithm_id", str)
    alg = _registry().algorithmById(alg_id)
    if alg is None:
        return {"found": False, "algorithm_id": alg_id, "safe": False}
    parameters = []
    for parameter in alg.parameterDefinitions():
        parameters.append({"name": parameter.name(), "description": parameter.description(), "type": parameter.type(), "optional": bool(parameter.flags() & parameter.FlagOptional)})
    outputs = [{"name": output.name(), "description": output.description(), "type": output.type()} for output in alg.outputDefinitions()]
    return {
        "found": True,
        "id": alg.id(),
        "name": alg.displayName(),
        "group": alg.group(),
        "provider": alg.provider().id() if alg.provider() else "",
        "safe": alg.id() in PROCESSING_ALLOWLIST,
        "parameters": parameters,
        "outputs": outputs,
        "suggested_wrapper_command": _suggest_wrapper_for_algorithm(alg.id()),
    }


def _suggest_wrapper_for_algorithm(alg_id: str) -> str:
    mapping = {
        "native:buffer": "buffer",
        "native:clip": "clip",
        "native:dissolve": "dissolve",
        "native:fixgeometries": "fix_geometries",
        "native:reprojectlayer": "reproject_layer",
        "native:intersection": "intersection",
        "native:union": "union",
        "native:difference": "difference",
        "native:centroids": "centroids",
        "native:multiparttosingleparts": "multipart_to_singleparts",
        "native:countpointsinpolygon": "count_points_in_polygon",
        "native:extractbyexpression": "extract_by_expression",
        "native:extractbyattribute": "extract_by_attribute",
        "native:extractbylocation": "extract_by_location",
    }
    return mapping.get(alg_id, "run_processing_with_allowlist")


def recommend_qgis_tool(params: dict[str, Any], context: dict[str, Any]):
    goal = require_param(params, "goal", str).lower()
    recommendations = []
    rules = [
        (["recortar", "clip", "cortar"], "clip", "native:clip"),
        (["buffer", "entorno", "distancia"], "buffer", "native:buffer"),
        (["dissolver", "dissolve"], "dissolve", "native:dissolve"),
        (["reprojetar", "reproject", "crs"], "reproject_layer", "native:reprojectlayer"),
        (["interse", "intersection"], "intersection", "native:intersection"),
        (["uniao", "união", "union"], "union", "native:union"),
        (["centroide", "centroid"], "centroids", "native:centroids"),
        (["atributo", "express", "filtrar", "selecionar"], "query_features", "native:extractbyexpression"),
        (["mapa", "layout", "cartograf"], "generate_professional_map", ""),
    ]
    for words, command, algorithm in rules:
        if any(word in goal for word in words):
            recommendations.append({"sigmai_command": command, "qgis_algorithm": algorithm, "risk": "low", "safe_default": True})
    if not recommendations:
        recommendations.append({"sigmai_command": "get_capabilities", "qgis_algorithm": "", "risk": "unknown", "safe_default": True, "note": "No direct match; inspect capabilities first."})
    return {"goal": goal, "recommendations": recommendations}
