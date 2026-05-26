from __future__ import annotations

from typing import Any

from ..security import ensure_parent_exists, normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param
from .common import project, qgis_imports


def handle(params: dict[str, Any], context: dict[str, Any]):
    layout_name = require_param(params, "layout_name", str)
    export_format = require_param(params, "format", str).lower()
    path_value = require_param(params, "path", str)
    confirm_overwrite = bool(params.get("confirm_overwrite", False))

    if export_format not in {"pdf", "png"}:
        raise ValidationError("BAD_REQUEST", "Unsupported export format.", {"format": export_format})

    output_path = normalize_output_path(path_value)
    ensure_parent_exists(output_path)
    try:
        reject_existing_path_without_confirmation(output_path, confirm_overwrite)
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc

    if context.get("dry_run"):
        return {
            "dry_run": True,
            "would_export_layout": layout_name,
            "format": export_format,
            "path": str(output_path),
            "changes": ["Export the named QGIS layout to the requested output file."],
        }

    layout = project().layoutManager().layoutByName(layout_name)
    if layout is None:
        raise ValidationError("LAYOUT_NOT_FOUND", "Layout not found.", {"layout_name": layout_name})

    exporter_class = qgis_imports()["QgsLayoutExporter"]
    exporter = exporter_class(layout)
    if export_format == "pdf":
        result = exporter.exportToPdf(str(output_path), exporter_class.PdfExportSettings())
    else:
        result = exporter.exportToImage(str(output_path), exporter_class.ImageExportSettings())

    if result != exporter_class.Success:
        raise ValidationError("EXPORT_FAILED", "QGIS layout export failed.", {"result": int(result)})

    return {"layout_name": layout_name, "format": export_format, "path": str(output_path)}
