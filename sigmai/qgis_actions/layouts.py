from __future__ import annotations

from typing import Any

from ..validators import ValidationError, require_param
from .common import project


def list_layouts(params: dict[str, Any], context: dict[str, Any]):
    layouts = []
    for layout in project().layoutManager().layouts():
        page_collection = layout.pageCollection()
        page_count = page_collection.pageCount() if page_collection else 0
        layouts.append({"name": layout.name(), "page_count": page_count})
    return {"layouts": layouts}


def create_layout(params: dict[str, Any], context: dict[str, Any]):
    name = require_param(params, "layout_name", str)
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "would_create_layout": name,
            "changes": ["Create a new QGIS print layout if it does not already exist."],
        }

    try:
        from qgis.core import QgsPrintLayout  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc

    manager = project().layoutManager()
    if manager.layoutByName(name) is not None:
        raise ValidationError("LAYOUT_ALREADY_EXISTS", "Layout already exists.", {"layout_name": name})

    layout = QgsPrintLayout(project())
    layout.initializeDefaults()
    layout.setName(name)
    manager.addLayout(layout)
    return {"layout_name": name, "created": True}
