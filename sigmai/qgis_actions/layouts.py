from __future__ import annotations

from typing import Any

from ..validators import ValidationError, require_param
from .common import project


def _describe_layout(layout: Any) -> dict[str, Any]:
    """Nome, páginas, itens e quadros de mapa de um layout.

    A ferramenta MCP prometia "tamanho de página e itens" e a ação devolvia só
    nome e contagem de páginas: um assistente que quisesse conferir se o
    inserto existia, ou em que escala o quadro estava, não tinha como.
    """
    page_collection = layout.pageCollection()
    page_count = page_collection.pageCount() if page_collection else 0
    pages = []
    for index in range(page_count):
        try:
            page = page_collection.page(index)
            size = page.pageSize()
            width, height = float(size.width()), float(size.height())
            pages.append({
                "width_mm": round(width, 1), "height_mm": round(height, 1),
                "orientation": "landscape" if width >= height else "portrait",
            })
        except Exception:
            continue
    items = []
    map_frames = []
    counters: dict[str, int] = {}
    for item in layout.items():
        try:
            item_id = str(item.id() or "")
        except Exception:
            continue
        type_name = type(item).__name__.replace("QgsLayoutItem", "").lower() or "item"
        id_missing = False
        if not item_id:
            # A interface do QGIS deixa o id vazio; descartar esses itens
            # descrevia um layout feito à mão como se estivesse vazio.
            if type_name not in {"map", "legend", "scalebar", "label", "picture"}:
                continue
            counters[type_name] = counters.get(type_name, 0) + 1
            item_id = f"{type_name}#{counters[type_name]}"
            id_missing = True
        entry: dict[str, Any] = {"id": item_id, "type": type_name}
        if id_missing:
            entry["id_missing"] = True
        try:
            position, size = item.positionWithUnits(), item.sizeWithUnits()
            entry.update({"x_mm": round(float(position.x()), 1), "y_mm": round(float(position.y()), 1),
                          "width_mm": round(float(size.width()), 1), "height_mm": round(float(size.height()), 1)})
        except Exception:
            pass
        if type(item).__name__ == "QgsLayoutItemMap":
            try:
                frame = {
                    "id": item_id,
                    "crs": str(item.crs().authid() or ""),
                    "scale": round(float(item.scale() or 0.0), 1),
                    "layers": [str(layer.name()) for layer in (item.layers() or [])],
                    "extent": {"xmin": item.extent().xMinimum(), "ymin": item.extent().yMinimum(),
                               "xmax": item.extent().xMaximum(), "ymax": item.extent().yMaximum()},
                    "grid_enabled": bool(item.grids().size() > 0 and item.grids().grid(0).enabled()),
                    "overviews": int(item.overviews().size()),
                }
                map_frames.append(frame)
            except Exception:
                map_frames.append({"id": item_id})
        elif type(item).__name__ == "QgsLayoutItemLabel":
            try:
                entry["text"] = str(item.text())[:200]
            except Exception:
                pass
        items.append(entry)
    return {"name": layout.name(), "page_count": page_count, "pages": pages, "items": items, "map_frames": map_frames}


def list_layouts(params: dict[str, Any], context: dict[str, Any]):
    return {"layouts": [_describe_layout(layout) for layout in project().layoutManager().layouts()]}


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
