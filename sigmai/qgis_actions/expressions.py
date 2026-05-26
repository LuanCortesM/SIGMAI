from __future__ import annotations

from typing import Any

from ..validators import ValidationError, require_param
from .attributes import _feature_to_dict
from .common import layer_type_name, project


def _imports() -> dict[str, Any]:
    try:
        from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc
    return locals()


def _vector_layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "This command requires a vector layer.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_LAYER", "Layer is invalid.", {"layer_id": layer_id})
    return layer


def _expression(expression_text: str):
    imports = _imports()
    expression = imports["QgsExpression"](expression_text)
    if expression.hasParserError():
        raise ValidationError("INVALID_EXPRESSION", "QGIS expression parser error.", {"expression": expression_text, "parser_error": expression.parserErrorString()})
    return expression


def _context(layer: Any):
    imports = _imports()
    context = imports["QgsExpressionContext"]()
    context.appendScopes(imports["QgsExpressionContextUtils"].globalProjectLayerScopes(layer))
    return context


def validate_expression(params: dict[str, Any], context: dict[str, Any]):
    expression_text = require_param(params, "expression", str)
    layer_id = params.get("layer_id")
    layer = _vector_layer(layer_id) if isinstance(layer_id, str) and layer_id else None
    expression = _expression(expression_text)
    prepared = None
    if layer is not None:
        expr_context = _context(layer)
        prepared = bool(expression.prepare(expr_context))
    return {"expression": expression_text, "valid": True, "prepared": prepared, "referenced_columns": sorted(expression.referencedColumns())}


def evaluate_expression(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    expression = _expression(require_param(params, "expression", str))
    max_features = int(params.get("max_features", 10))
    if max_features <= 0 or max_features > 500:
        raise ValidationError("BAD_REQUEST", "max_features must be between 1 and 500.", {"max_features": max_features})
    expr_context = _context(layer)
    expression.prepare(expr_context)
    results = []
    for feature in layer.getFeatures():
        expr_context.setFeature(feature)
        value = expression.evaluate(expr_context)
        if expression.hasEvalError():
            raise ValidationError("EXPRESSION_EVAL_ERROR", "QGIS expression evaluation error.", {"eval_error": expression.evalErrorString()})
        results.append({"feature_id": feature.id(), "value": value if isinstance(value, (str, int, float, bool)) or value is None else str(value)})
        if len(results) >= max_features:
            break
    return {"layer_id": layer.id(), "expression": expression.expression(), "returned": len(results), "results": results, "truncated": int(layer.featureCount()) > len(results)}


def query_features(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    expression = _expression(require_param(params, "expression", str))
    max_features = int(params.get("max_features", params.get("limit", 100)))
    include_geometry = bool(params.get("include_geometry", False))
    if max_features <= 0 or max_features > 1000:
        raise ValidationError("BAD_REQUEST", "max_features must be between 1 and 1000.", {"max_features": max_features})
    expr_context = _context(layer)
    expression.prepare(expr_context)
    field_names = [field.name() for field in layer.fields()]
    features = []
    checked = 0
    for feature in layer.getFeatures():
        checked += 1
        expr_context.setFeature(feature)
        value = expression.evaluate(expr_context)
        if expression.hasEvalError():
            raise ValidationError("EXPRESSION_EVAL_ERROR", "QGIS expression evaluation error.", {"eval_error": expression.evalErrorString()})
        if bool(value):
            features.append(_feature_to_dict(feature, field_names, include_geometry=include_geometry))
            if len(features) >= max_features:
                break
    return {"layer_id": layer.id(), "expression": expression.expression(), "checked": checked, "matched_returned": len(features), "features": features, "truncated": len(features) >= max_features}
