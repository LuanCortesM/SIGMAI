from __future__ import annotations

from pathlib import Path
from typing import Any

from ..security import normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param
from .common import qgis_imports
from .gis_tools import PROCESSING_ALLOWLIST


def _check_outputs(parameters: dict[str, Any], confirm_overwrite: bool) -> None:
    for key, value in parameters.items():
        upper_key = key.upper()
        if "OUTPUT" not in upper_key:
            continue
        if not isinstance(value, str) or value == "TEMPORARY_OUTPUT":
            continue
        output_path = normalize_output_path(value)
        try:
            reject_existing_path_without_confirmation(output_path, confirm_overwrite)
        except FileExistsError as exc:
            raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc
        if output_path.parent and not output_path.parent.exists():
            raise ValidationError("BAD_REQUEST", "Output directory does not exist.", {"path": str(output_path.parent)})


def handle(params: dict[str, Any], context: dict[str, Any]):
    algorithm = require_param(params, "algorithm", str)
    parameters = require_param(params, "parameters", dict)
    confirm_overwrite = bool(params.get("confirm_overwrite", False))
    if algorithm not in PROCESSING_ALLOWLIST:
        raise ValidationError(
            "PROCESSING_ALGORITHM_BLOCKED",
            "Algorithm is not in the SIGMAI Processing allowlist. Prefer high-level GIS commands when available.",
            {"algorithm": algorithm, "allowlist": sorted(PROCESSING_ALLOWLIST)},
        )
    _check_outputs(parameters, confirm_overwrite)

    if context.get("dry_run"):
        return {
            "dry_run": True,
            "would_run_algorithm": algorithm,
            "parameters": parameters,
            "changes": ["Run the QGIS Processing algorithm with the provided parameters."],
        }

    imports = qgis_imports()
    registry = imports["QgsApplication"].processingRegistry()
    if registry.algorithmById(algorithm) is None:
        raise ValidationError(
            "PROCESSING_ALGORITHM_NOT_FOUND",
            "Processing algorithm was not found.",
            {"algorithm": algorithm},
        )

    try:
        import processing  # type: ignore
    except Exception as exc:
        raise ValidationError("PROCESSING_NOT_AVAILABLE", "QGIS Processing is not available.", {}) from exc

    result = processing.run(algorithm, parameters)
    serializable_result = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in result.items()
    }
    return {"algorithm": algorithm, "result": serializable_result}
