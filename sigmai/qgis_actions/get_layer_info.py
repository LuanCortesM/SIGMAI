from __future__ import annotations

from typing import Any

from ..validators import ValidationError, require_param
from .common import crs_authid, extent_to_dict, layer_type_name, project


def handle(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})

    fields = []
    if layer_type_name(layer) == "vector" and hasattr(layer, "fields"):
        fields = [
            {"name": field.name(), "type": field.typeName()}
            for field in layer.fields()
        ]

    return {
        "id": layer.id(),
        "name": layer.name(),
        "type": layer_type_name(layer),
        "crs": crs_authid(layer.crs()) if hasattr(layer, "crs") else "",
        "extent": extent_to_dict(layer),
        "fields": fields,
        "valid": bool(layer.isValid()),
        "source": layer.source() if hasattr(layer, "source") else "",
    }
