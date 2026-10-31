from __future__ import annotations

from typing import Any

from ..validators import ValidationError, require_param
from .common import layer_type_name, project
from .expressions import _context, _expression
from .gis_tools import _check_output, _processing_run, _serialize_processing_result


PREDICATE_CODES = {
    "intersects": 0,
    "contains": 1,
    "equals": 2,
    "touches": 3,
    "overlaps": 4,
    "within": 5,
    "crosses": 6,
}


def _vector_layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "This command requires a vector layer.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_LAYER", "Layer is invalid.", {"layer_id": layer_id})
    return layer


def _predicate(params: dict[str, Any]) -> list[int]:
    raw = params.get("predicate", params.get("predicates", "intersects"))
    if isinstance(raw, str):
        raw_values = [raw]
    elif isinstance(raw, list):
        raw_values = raw
    else:
        raise ValidationError("BAD_REQUEST", "predicate must be a string or list.", {"predicate": raw})
    codes = []
    for value in raw_values:
        key = str(value).lower()
        if key not in PREDICATE_CODES:
            raise ValidationError("BAD_REQUEST", "Unsupported spatial predicate.", {"predicate": value, "supported": sorted(PREDICATE_CODES)})
        codes.append(PREDICATE_CODES[key])
    return codes


def _matching_ids(layer: Any, expression_text: str, max_features: int | None = None) -> tuple[list[int], bool]:
    """Ids das feições que satisfazem a expressão, na camada inteira; ``truncated`` se ``max_features`` cortou.

    Lia só as 100.000 primeiras feições, sem dizer: nos 362.210 registros do
    GBIF, a simulação de extract_by_expression contou 48.425 em vez de
    115.494, e select_by_expression selecionava só entre as primeiras.
    """
    from qgis.core import QgsFeatureRequest  # type: ignore

    from ..cartography.qtcompat import qt_enum

    expression = _expression(expression_text)
    expr_context = _context(layer)
    expression.prepare(expr_context)
    request = QgsFeatureRequest()
    if not expression.needsGeometry():
        request.setFlags(qt_enum(QgsFeatureRequest, "Flag", "NoGeometry"))
    request.setSubsetOfAttributes(expression.referencedColumns(), layer.fields())
    ids: list[int] = []
    checked = 0
    for feature in layer.getFeatures(request):
        if max_features is not None and checked >= max_features:
            return ids, True
        checked += 1
        expr_context.setFeature(feature)
        if bool(expression.evaluate(expr_context)):
            ids.append(feature.id())
        if expression.hasEvalError():
            raise ValidationError("EXPRESSION_EVAL_ERROR", "QGIS expression evaluation error.", {"eval_error": expression.evalErrorString()})
    return ids, False


def _max_features(params: dict[str, Any]) -> int | None:
    value = params.get("max_features")
    return None if value in (None, "") else max(1, int(value))


def select_by_expression(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    expression = require_param(params, "expression", str)
    ids, truncated = _matching_ids(layer, expression, _max_features(params))
    before = len(layer.selectedFeatureIds())
    extra = {"truncated_at_max_features": True} if truncated else {}
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "expression": expression, "would_select_count": len(ids), "sample_feature_ids": ids[:50], "before_selected_count": before, **extra}
    layer.selectByIds(ids)
    return {"layer_id": layer.id(), "expression": expression, "selected_count": len(layer.selectedFeatureIds()), "before_selected_count": before, "sample_feature_ids": ids[:50], **extra}


def select_by_attribute(params: dict[str, Any], context: dict[str, Any]):
    field_name = require_param(params, "field_name", str)
    operator = str(params.get("operator", "=")).strip()
    value = params.get("value")
    allowed = {"=", "!=", ">", ">=", "<", "<=", "LIKE", "ILIKE"}
    if operator.upper() not in allowed:
        raise ValidationError("BAD_REQUEST", "Unsupported attribute operator.", {"operator": operator, "supported": sorted(allowed)})
    quoted = str(value).replace("'", "''")
    if isinstance(value, (int, float)):
        literal = str(value)
    else:
        literal = f"'{quoted}'"
    expression = f"\"{field_name}\" {operator} {literal}"
    return select_by_expression({**params, "expression": expression}, context)


def select_by_location(params: dict[str, Any], context: dict[str, Any]):
    input_layer = _vector_layer(require_param(params, "input_layer_id", str))
    overlay_layer = _vector_layer(require_param(params, "overlay_layer_id", str))
    predicates = _predicate(params)
    if context.get("dry_run"):
        return {"dry_run": True, "input_layer_id": input_layer.id(), "overlay_layer_id": overlay_layer.id(), "predicates": predicates, "changes": ["Select matching features in the input layer."]}
    output = _processing_run("native:extractbylocation", {"INPUT": input_layer, "PREDICATE": predicates, "INTERSECT": overlay_layer, "OUTPUT": "TEMPORARY_OUTPUT"})
    output_layer = output.get("OUTPUT")
    ids = []
    if hasattr(output_layer, "getFeatures"):
        source_ids = {feature.id() for feature in output_layer.getFeatures()}
        ids = list(source_ids)
    input_layer.selectByIds(ids)
    return {"input_layer_id": input_layer.id(), "overlay_layer_id": overlay_layer.id(), "selected_count": len(ids), "predicates": predicates}


def extract_by_expression(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    expression = require_param(params, "expression", str)
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    if context.get("dry_run"):
        ids, truncated = _matching_ids(layer, expression, _max_features(params))
        return {"dry_run": True, "layer_id": layer.id(), "expression": expression, "would_extract_count": len(ids), "output": output,
                **({"truncated_at_max_features": True} if truncated else {})}
    result = _processing_run("native:extractbyexpression", {"INPUT": layer, "EXPRESSION": expression, "OUTPUT": output})
    return {"algorithm": "native:extractbyexpression", "result": _serialize_processing_result(result)}


def extract_by_attribute(params: dict[str, Any], context: dict[str, Any]):
    field_name = require_param(params, "field_name", str)
    operator = str(params.get("operator", "=")).strip()
    value = params.get("value")
    quoted = str(value).replace("'", "''")
    literal = str(value) if isinstance(value, (int, float)) else f"'{quoted}'"
    return extract_by_expression({**params, "expression": f"\"{field_name}\" {operator} {literal}"}, context)


def extract_by_location(params: dict[str, Any], context: dict[str, Any]):
    input_layer = _vector_layer(require_param(params, "input_layer_id", str))
    overlay_layer = _vector_layer(require_param(params, "overlay_layer_id", str))
    predicates = _predicate(params)
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    if context.get("dry_run"):
        return {"dry_run": True, "input_layer_id": input_layer.id(), "overlay_layer_id": overlay_layer.id(), "predicates": predicates, "output": output}
    result = _processing_run("native:extractbylocation", {"INPUT": input_layer, "PREDICATE": predicates, "INTERSECT": overlay_layer, "OUTPUT": output})
    return {"algorithm": "native:extractbylocation", "result": _serialize_processing_result(result)}
