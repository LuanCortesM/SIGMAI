from __future__ import annotations

import math
from typing import Any

from ..validators import ValidationError, require_param
from .common import layer_type_name, project


def _vector_layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "This command requires a vector layer.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_LAYER", "Layer is invalid.", {"layer_id": layer_id})
    return layer


def _field_index(layer: Any, field_name: str) -> int:
    idx = layer.fields().indexFromName(field_name)
    if idx < 0:
        raise ValidationError("FIELD_NOT_FOUND", "Field not found.", {"field_name": field_name})
    return idx


def _value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return str(value)


def _feature_to_dict(feature: Any, field_names: list[str], include_geometry: bool = False) -> dict[str, Any]:
    attrs = feature.attributes()
    item = {"feature_id": feature.id(), "attributes": {name: _value(attrs[i]) for i, name in enumerate(field_names)}}
    if include_geometry:
        geom = feature.geometry()
        item["geometry"] = geom.asWkt() if geom and not geom.isNull() else None
    return item


def list_fields(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    fields = []
    for field in layer.fields():
        fields.append(
            {
                "name": field.name(),
                "type": field.typeName(),
                "length": field.length(),
                "precision": field.precision(),
                "is_numeric": field.isNumeric(),
            }
        )
    return {"layer_id": layer.id(), "layer_name": layer.name(), "feature_count": int(layer.featureCount()), "fields": fields}


def sample_features(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    max_features = int(params.get("max_features", params.get("limit", 10)))
    include_geometry = bool(params.get("include_geometry", False))
    if max_features <= 0 or max_features > 500:
        raise ValidationError("BAD_REQUEST", "max_features must be between 1 and 500.", {"max_features": max_features})
    field_names = [field.name() for field in layer.fields()]
    features = []
    for feature in layer.getFeatures():
        features.append(_feature_to_dict(feature, field_names, include_geometry=include_geometry))
        if len(features) >= max_features:
            break
    return {
        "layer_id": layer.id(),
        "layer_name": layer.name(),
        "feature_count": int(layer.featureCount()),
        "returned": len(features),
        "fields": field_names,
        "features": features,
        "truncated": int(layer.featureCount()) > len(features),
    }


def inspect_attribute_table(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    sample_limit = int(params.get("sample_limit", 5))
    fields_payload = list_fields({"layer_id": layer.id()}, context)
    sample_payload = sample_features({"layer_id": layer.id(), "max_features": sample_limit}, context)
    warnings = []
    if int(layer.featureCount()) > 10000:
        warnings.append("Large layer: table inspection returns schema and bounded sample only.")
    return {"layer_id": layer.id(), "layer_name": layer.name(), "feature_count": int(layer.featureCount()), "fields": fields_payload["fields"], "sample": sample_payload["features"], "warnings": warnings}


def unique_values(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    field_name = require_param(params, "field_name", str)
    limit = int(params.get("limit", 100))
    if limit <= 0 or limit > 1000:
        raise ValidationError("BAD_REQUEST", "limit must be between 1 and 1000.", {"limit": limit})
    idx = _field_index(layer, field_name)
    values = []
    for value in layer.uniqueValues(idx, limit):
        values.append(_value(value))
        if len(values) >= limit:
            break
    return {"layer_id": layer.id(), "field_name": field_name, "limit": limit, "unique_values": values, "returned": len(values)}


def field_statistics(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    field_name = require_param(params, "field_name", str)
    max_features = int(params.get("max_features", 10000))
    idx = _field_index(layer, field_name)
    values: list[Any] = []
    numeric: list[float] = []
    null_count = 0
    checked = 0
    for feature in layer.getFeatures():
        if checked >= max_features:
            break
        checked += 1
        value = feature.attribute(idx)
        if value is None:
            null_count += 1
            continue
        values.append(_value(value))
        try:
            numeric.append(float(value))
        except Exception:
            pass
    result: dict[str, Any] = {
        "layer_id": layer.id(),
        "field_name": field_name,
        "feature_count": int(layer.featureCount()),
        "checked": checked,
        "null_count": null_count,
        "non_null_count": len(values),
        "reached_limit": int(layer.featureCount()) > checked,
    }
    if numeric and len(numeric) == len(values):
        result.update(
            {
                "numeric": True,
                "min": min(numeric),
                "max": max(numeric),
                "mean": sum(numeric) / len(numeric),
            }
        )
    else:
        counts: dict[str, int] = {}
        for value in values:
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
        result.update({"numeric": False, "distinct_sample_count": len(counts), "top_values": sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:20]})
    return result
