from __future__ import annotations

from .common import project, summarize_layer


def handle(params, context):
    layers = [summarize_layer(layer) for layer in project().mapLayers().values()]
    warnings = []
    invalid = [layer for layer in layers if not layer["valid"]]
    missing_crs = [layer for layer in layers if not layer.get("crs")]
    if invalid:
        warnings.append(f"{len(invalid)} invalid layer(s) detected.")
    if missing_crs:
        warnings.append(f"{len(missing_crs)} layer(s) without CRS detected.")
    return {
        "layers": layers,
        "invalid_layer_ids": [layer["id"] for layer in invalid],
        "layers_without_crs": [layer["id"] for layer in missing_crs],
        "diagnostics": warnings,
    }
