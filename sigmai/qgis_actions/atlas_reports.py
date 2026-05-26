from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..security import ensure_parent_exists, normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param
from .common import crs_authid, extent_to_dict, layer_type_name, project


_REPORT_SECTIONS: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _vector_layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "This command requires a vector layer.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_LAYER", "Layer is invalid.", {"layer_id": layer_id})
    return layer


def _field_names(layer: Any) -> list[str]:
    return [field.name() for field in layer.fields()]


def create_atlas(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "coverage_layer_id", str))
    name = str(params.get("atlas_name") or params.get("layout_name") or f"SIGMAI Atlas {layer.name()}")
    title_field = str(params.get("title_field", ""))
    if title_field and title_field not in _field_names(layer):
        raise ValidationError("FIELD_NOT_FOUND", "title_field was not found in coverage layer.", {"field": title_field})
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "atlas_name": name,
            "coverage_layer_id": layer.id(),
            "coverage_layer_name": layer.name(),
            "title_field": title_field,
            "changes": ["Create a SIGMAI atlas configuration object without modifying source data."],
        }
    atlas = {
        "atlas_name": name,
        "coverage_layer_id": layer.id(),
        "coverage_layer_name": layer.name(),
        "title_field": title_field,
        "feature_count": layer.featureCount(),
        "crs": crs_authid(layer.crs()),
        "extent": extent_to_dict(layer),
        "created_at": _now(),
        "status": "configured",
        "note": "Initial SIGMAI atlas stores a safe configuration. Formal QgsLayoutAtlas batch export is a later runner phase.",
    }
    _REPORT_SECTIONS.setdefault(name, {"type": "atlas", "sections": []})["atlas"] = atlas
    return atlas


def configure_atlas_coverage_layer(params: dict[str, Any], context: dict[str, Any]):
    return create_atlas(params, context)


def set_atlas_filter_expression(params: dict[str, Any], context: dict[str, Any]):
    atlas_name = require_param(params, "atlas_name", str)
    expression = require_param(params, "expression", str)
    if context.get("dry_run"):
        return {"dry_run": True, "atlas_name": atlas_name, "expression": expression}
    entry = _REPORT_SECTIONS.setdefault(atlas_name, {"type": "atlas", "sections": []})
    entry["filter_expression"] = expression
    return {"atlas_name": atlas_name, "filter_expression": expression}


def set_atlas_sort_expression(params: dict[str, Any], context: dict[str, Any]):
    atlas_name = require_param(params, "atlas_name", str)
    expression = require_param(params, "expression", str)
    if context.get("dry_run"):
        return {"dry_run": True, "atlas_name": atlas_name, "expression": expression}
    entry = _REPORT_SECTIONS.setdefault(atlas_name, {"type": "atlas", "sections": []})
    entry["sort_expression"] = expression
    return {"atlas_name": atlas_name, "sort_expression": expression}


def generate_map_book(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "coverage_layer_id", str))
    limit = max(1, min(int(params.get("limit", 5)), 50))
    name_field = str(params.get("name_field", ""))
    if name_field and name_field not in _field_names(layer):
        raise ValidationError("FIELD_NOT_FOUND", "name_field was not found in coverage layer.", {"field": name_field})
    pages = []
    for index, feature in enumerate(layer.getFeatures(), start=1):
        if index > limit:
            break
        label = str(feature[name_field]) if name_field else f"Feature {feature.id()}"
        pages.append({"page": index, "feature_id": int(feature.id()), "label": label})
    return {
        "map_book_name": params.get("map_book_name", f"SIGMAI Map Book {layer.name()}"),
        "coverage_layer_id": layer.id(),
        "coverage_layer_name": layer.name(),
        "page_count": len(pages),
        "pages": pages,
        "dry_run": bool(context.get("dry_run")),
        "note": "This is a safe map-book plan. Real per-page atlas export is reserved for the atlas runner phase.",
    }


def export_atlas_pdf(params: dict[str, Any], context: dict[str, Any]):
    return _atlas_export_plan(params, context, "pdf")


def export_atlas_images(params: dict[str, Any], context: dict[str, Any]):
    return _atlas_export_plan(params, context, "images")


def _atlas_export_plan(params: dict[str, Any], context: dict[str, Any], export_type: str):
    atlas_name = require_param(params, "atlas_name", str)
    if not context.get("dry_run"):
        raise ValidationError(
            "ATLAS_EXPORT_NOT_ENABLED",
            "Formal atlas batch export is not enabled until the job/atlas runner can drive QgsLayoutAtlas safely.",
            {"atlas_name": atlas_name, "export_type": export_type},
        )
    return {
        "dry_run": True,
        "atlas_name": atlas_name,
        "export_type": export_type,
        "changes": ["Would export atlas pages without modifying source data."],
    }


def create_report(params: dict[str, Any], context: dict[str, Any]):
    report_name = str(params.get("report_name") or params.get("title") or "SIGMAI Technical Report")
    if context.get("dry_run"):
        return {"dry_run": True, "report_name": report_name, "changes": ["Create an in-memory report container."]}
    _REPORT_SECTIONS[report_name] = {
        "type": "technical_report",
        "report_name": report_name,
        "title": report_name,
        "created_at": _now(),
        "sections": [],
    }
    return _REPORT_SECTIONS[report_name]


def add_report_section(params: dict[str, Any], context: dict[str, Any]):
    report_name = require_param(params, "report_name", str)
    title = require_param(params, "title", str)
    body = str(params.get("body", ""))
    section = {"title": title, "body": body, "created_at": _now()}
    if context.get("dry_run"):
        return {"dry_run": True, "report_name": report_name, "section": section}
    report = _REPORT_SECTIONS.setdefault(report_name, {"type": "technical_report", "report_name": report_name, "title": report_name, "created_at": _now(), "sections": []})
    report.setdefault("sections", []).append(section)
    return {"report_name": report_name, "section_count": len(report["sections"]), "section": section}


def export_report_html(params: dict[str, Any], context: dict[str, Any]):
    return _export_report(params, context, "html")


def export_report_pdf(params: dict[str, Any], context: dict[str, Any]):
    if not context.get("dry_run"):
        raise ValidationError("REPORT_PDF_NOT_ENABLED", "PDF report export is planned after HTML/Markdown report validation.", {})
    return _export_report(params, context, "pdf")


def generate_workflow_report_pdf(params: dict[str, Any], context: dict[str, Any]):
    return export_report_pdf(params, context)


def generate_analysis_report(params: dict[str, Any], context: dict[str, Any]):
    report_name = str(params.get("report_name", "SIGMAI Analysis Report"))
    if not context.get("dry_run"):
        _REPORT_SECTIONS[report_name] = {
            "type": "analysis_report",
            "report_name": report_name,
            "title": report_name,
            "created_at": _now(),
            "sections": [
                {"title": "Environment", "body": "Generated by SIGMAI using local QGIS session."},
                {"title": "Security", "body": "Local bridge, bearer token, no arbitrary Python execution."},
            ],
        }
    return {"report_name": report_name, "dry_run": bool(context.get("dry_run")), "section_count": 2}


def _export_report(params: dict[str, Any], context: dict[str, Any], fmt: str):
    report_name = require_param(params, "report_name", str)
    output_path = normalize_output_path(require_param(params, "output_path", str))
    confirm_overwrite = bool(params.get("confirm_overwrite"))
    ensure_parent_exists(output_path)
    try:
        reject_existing_path_without_confirmation(output_path, confirm_overwrite)
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc
    report = _REPORT_SECTIONS.get(report_name) or {
        "type": "technical_report",
        "report_name": report_name,
        "title": report_name,
        "created_at": _now(),
        "sections": [{"title": "Summary", "body": "SIGMAI report container was created at export time."}],
    }
    if context.get("dry_run"):
        return {"dry_run": True, "report_name": report_name, "format": fmt, "output_path": str(output_path)}
    if fmt == "html":
        body = "\n".join(f"<h2>{section.get('title', '')}</h2><p>{section.get('body', '')}</p>" for section in report.get("sections", []))
        output_path.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>{report_name}</title></head><body><h1>{report_name}</h1>{body}</body></html>", encoding="utf-8")
    else:
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report_name": report_name, "format": fmt, "output_path": str(output_path), "size": output_path.stat().st_size}
