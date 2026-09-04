"""Lê um layout do QGIS e produz a *observação* que o regulamento avalia.

Separar a leitura da avaliação tem duas consequências práticas: o regulamento
pode ser testado sem QGIS, e o laudo passa a ser reproduzível — a mesma
observação sempre gera o mesmo laudo, o que permite guardar observações como
casos de teste de regressão cartográfica.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .pagespec import PageSpec

#: Papéis atribuídos por identificador de item. O compositor do SIGMAI nomeia
#: seus itens; layouts feitos à mão pelo usuário são classificados pelo tipo.
ROLE_BY_ITEM_ID = {
    "main_map": "map",
    "title": "title",
    "subtitle": "subtitle",
    "source": "source",
    "footer": "source",
    "credits": "source",
    "legend": "legend",
    "scale_bar": "scalebar",
    "scale_text": "scale_text",
    "north_arrow": "north",
    "crs_note": "crs_note",
    "logo": "logo",
    "inset_map": "inset",
}


def _safe(callable_obj: Any, default: Any = None) -> Any:
    try:
        return callable_obj()
    except Exception:
        return default


def _rect_dict(rect: Any) -> dict[str, float] | None:
    if rect is None:
        return None
    try:
        if rect.isEmpty():
            return None
        return {
            "xmin": float(rect.xMinimum()),
            "ymin": float(rect.yMinimum()),
            "xmax": float(rect.xMaximum()),
            "ymax": float(rect.yMaximum()),
        }
    except Exception:
        return None


def observe_layout(
    layout: Any,
    *,
    output_path: str | None = None,
    page_spec: PageSpec | None = None,
    data_extent: dict[str, float] | None = None,
    ink_fraction: float | None = None,
) -> dict[str, Any]:
    """Descreve um ``QgsPrintLayout`` como dicionário puro."""
    observation: dict[str, Any] = {
        "layout_name": _safe(layout.name, ""),
        "page": _observe_page(layout, page_spec),
        "items": [],
        "map": {},
        "legend": None,
        "scalebar": None,
        "north": None,
        "output": _observe_output(output_path),
    }

    map_item = None
    legend_item = None
    scalebar_item = None
    north_item = None

    for item in _safe(layout.items, []) or []:
        item_id = _safe(getattr(item, "id", lambda: ""), "") or ""
        if not item_id:
            continue
        entry = _observe_item(item, item_id)
        observation["items"].append(entry)
        role = entry.get("role")
        if role == "map" and map_item is None:
            map_item = item
        elif role == "legend" and legend_item is None:
            legend_item = item
        elif role == "scalebar" and scalebar_item is None:
            scalebar_item = item
        elif role == "north" and north_item is None:
            north_item = item

    if map_item is not None:
        observation["map"] = _observe_map(map_item, data_extent, ink_fraction)
    if legend_item is not None:
        observation["legend"] = _observe_legend(legend_item)
    if scalebar_item is not None:
        observation["scalebar"] = _observe_scalebar(scalebar_item, map_item, observation["items"])
    if north_item is not None:
        observation["north"] = _observe_north(north_item)

    return observation


def _observe_page(layout: Any, page_spec: PageSpec | None) -> dict[str, Any]:
    if page_spec is not None:
        return page_spec.to_dict()
    try:
        page = layout.pageCollection().page(0)
        size = page.pageSize()
        width, height = float(size.width()), float(size.height())
    except Exception:
        width, height = 297.0, 210.0
    # Sem PageSpec explícito, assume a margem padrão do SIGMAI para poder
    # avaliar CART041 sem inventar um número diferente a cada execução.
    margin = max(5.0, round(min(width, height) * 0.048, 1))
    return {
        "name": "desconhecida",
        "orientation": "landscape" if width >= height else "portrait",
        "width_mm": round(width, 2),
        "height_mm": round(height, 2),
        "margins_mm": {"top": margin, "right": margin, "bottom": margin, "left": margin},
        "content_area_mm": {
            "x": margin,
            "y": margin,
            "width": round(width - 2 * margin, 2),
            "height": round(height - 2 * margin, 2),
        },
    }


def _observe_item(item: Any, item_id: str) -> dict[str, Any]:
    class_name = type(item).__name__
    type_name = {
        "QgsLayoutItemMap": "map",
        "QgsLayoutItemLegend": "legend",
        "QgsLayoutItemScaleBar": "scalebar",
        "QgsLayoutItemLabel": "label",
        "QgsLayoutItemPicture": "picture",
        "QgsLayoutItemShape": "shape",
    }.get(class_name, class_name)

    entry: dict[str, Any] = {"id": item_id, "type": type_name, "class": class_name}

    position = _safe(item.positionWithUnits)
    size = _safe(item.sizeWithUnits)
    if position is not None and size is not None:
        entry.update({
            "x": round(float(position.x()), 2),
            "y": round(float(position.y()), 2),
            "width": round(float(size.width()), 2),
            "height": round(float(size.height()), 2),
        })
    else:
        rect = _safe(item.sceneBoundingRect)
        if rect is not None:
            entry.update({
                "x": round(float(rect.left()), 2),
                "y": round(float(rect.top()), 2),
                "width": round(float(rect.width()), 2),
                "height": round(float(rect.height()), 2),
            })

    if type_name == "label":
        entry["text"] = _safe(item.text, "") or ""
        font = _safe(item.font)
        if font is not None:
            size_pt = _safe(font.pointSizeF, -1.0)
            if size_pt and size_pt > 0:
                entry["font_size_pt"] = round(float(size_pt), 1)
        # QGIS ≥3.24 usa QgsTextFormat, que sobrepõe a QFont.
        text_format = _safe(getattr(item, "textFormat", None))
        if text_format is not None:
            format_size = _safe(text_format.size, None)
            if format_size and float(format_size) > 0:
                entry["font_size_pt"] = round(float(format_size), 1)

    entry["role"] = _role_for(item_id, type_name, entry.get("text", ""))
    return entry


def _role_for(item_id: str, type_name: str, text: str) -> str:
    if item_id in ROLE_BY_ITEM_ID:
        return ROLE_BY_ITEM_ID[item_id]
    lowered = item_id.lower()
    for key, role in ROLE_BY_ITEM_ID.items():
        if key in lowered:
            return role
    if type_name in {"map", "legend", "scalebar"}:
        return {"map": "map", "legend": "legend", "scalebar": "scalebar"}[type_name]
    if type_name == "picture" and ("north" in lowered or "norte" in lowered):
        return "north"
    if type_name == "label" and "1:" in str(text):
        return "scale_text"
    return type_name


def _observe_map(map_item: Any, data_extent: dict[str, float] | None, ink_fraction: float | None) -> dict[str, Any]:
    crs = _safe(map_item.crs)
    layers = _safe(map_item.layers, []) or []
    grid = _safe(map_item.grid)

    info: dict[str, Any] = {
        "item_id": _safe(map_item.id, "") or "",
        "crs": _safe(crs.authid, "") if crs is not None else "",
        "crs_description": _safe(crs.description, "") if crs is not None else "",
        "crs_is_geographic": _safe(crs.isGeographic, None) if crs is not None else None,
        "scale": round(float(_safe(map_item.scale, 0.0) or 0.0), 1),
        "rotation": float(_safe(map_item.mapRotation, 0.0) or 0.0),
        "extent": _rect_dict(_safe(map_item.extent)),
        "visible_layer_ids": [str(_safe(layer.id, "")) for layer in layers],
        "visible_layer_names": [str(_safe(layer.name, "")) for layer in layers],
        "data_extent": data_extent,
        "rendered_ink_fraction": ink_fraction,
    }

    if grid is not None:
        info["grid"] = {
            "enabled": bool(_safe(grid.enabled, False)),
            "interval_x": float(_safe(grid.intervalX, 0.0) or 0.0),
            "interval_y": float(_safe(grid.intervalY, 0.0) or 0.0),
            "annotations": bool(_safe(grid.annotationEnabled, False)),
        }
    else:
        info["grid"] = {"enabled": False, "interval_x": 0.0, "interval_y": 0.0, "annotations": False}

    return info


def _observe_legend(legend_item: Any) -> dict[str, Any]:
    names: list[str] = []
    try:
        model = legend_item.model()
        root = model.rootGroup()
        for node in root.findLayers():
            layer = node.layer()
            if layer is not None:
                names.append(str(layer.name()))
            else:
                names.append(str(node.name()))
    except Exception:
        pass
    return {
        "item_id": _safe(legend_item.id, "") or "",
        "title": _safe(legend_item.title, "") or "",
        "layer_names": names,
        "auto_update": bool(_safe(legend_item.autoUpdateModel, True)),
        "column_count": int(_safe(legend_item.columnCount, 1) or 1),
    }


def _observe_scalebar(scalebar_item: Any, map_item: Any, items: list[dict[str, Any]]) -> dict[str, Any]:
    unit_label = _safe(scalebar_item.unitLabel, "") or ""
    units_per_segment = float(_safe(scalebar_item.unitsPerSegment, 0.0) or 0.0)
    segments = int(_safe(scalebar_item.numberOfSegments, 0) or 0)
    segments_left = int(_safe(scalebar_item.numberOfSegmentsLeft, 0) or 0)

    bar_entry = next((item for item in items if item.get("role") == "scalebar"), {})
    map_entry = next((item for item in items if item.get("role") == "map"), {})
    frame_width = float(map_entry.get("width") or 0.0)

    # A largura útil da barra é a soma dos segmentos convertida para milímetros
    # de papel, e não a largura da caixa do item — a caixa costuma ser maior.
    bar_width_mm = None
    fraction = None
    scale = float(_safe(map_item.scale, 0.0) or 0.0) if map_item is not None else 0.0
    factor = {"km": 1000.0, "m": 1.0, "cm": 0.01, "mi": 1609.344, "ft": 0.3048}.get(unit_label.strip().lower())
    if scale > 0 and factor and units_per_segment > 0 and (segments + segments_left) > 0:
        total_ground = units_per_segment * (segments + segments_left) * factor
        bar_width_mm = (total_ground / scale) * 1000.0
        if frame_width > 0:
            fraction = bar_width_mm / frame_width

    return {
        "item_id": _safe(scalebar_item.id, "") or "",
        "unit": unit_label.strip().lower(),
        "unit_label": unit_label,
        "units_per_segment": units_per_segment,
        "segments": segments,
        "segments_left": segments_left,
        "box_width_mm": bar_entry.get("width"),
        "bar_width_mm": round(bar_width_mm, 2) if bar_width_mm else None,
        "frame_fraction": round(fraction, 4) if fraction else None,
    }


def _observe_north(north_item: Any) -> dict[str, Any]:
    class_name = type(north_item).__name__
    kind = "picture" if class_name == "QgsLayoutItemPicture" else "label" if class_name == "QgsLayoutItemLabel" else class_name
    info: dict[str, Any] = {"item_id": _safe(north_item.id, "") or "", "kind": kind}
    if kind == "picture":
        info["path"] = _safe(getattr(north_item, "picturePath", None), "") or ""
        mode = _safe(getattr(north_item, "northMode", None), None)
        info["north_mode"] = str(mode) if mode is not None else ""
        info["linked_map"] = bool(_safe(getattr(north_item, "linkedMap", None), None))
    else:
        info["text"] = _safe(getattr(north_item, "text", None), "") or ""
    return info


def _observe_output(output_path: str | None) -> dict[str, Any]:
    if not output_path:
        return {}
    path = Path(output_path)
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "format": path.suffix.lstrip(".").lower(),
    }


def measure_ink_fraction(png_path: str | Path, map_rect_mm: dict[str, float], page_mm: tuple[float, float]) -> float | None:
    """Fração de pixels não-fundo dentro do quadro do mapa no PNG exportado.

    É a única checagem que enxerga o resultado em vez de confiar na estrutura
    de dados; sem ela, um mapa em branco passa por todos os códigos de retorno.
    """
    try:
        from qgis.PyQt.QtGui import QImage  # type: ignore
    except Exception:
        return None

    image = QImage(str(png_path))
    if image.isNull():
        return None

    page_width, page_height = page_mm
    if page_width <= 0 or page_height <= 0:
        return None

    scale_x = image.width() / page_width
    scale_y = image.height() / page_height
    left = max(0, int(map_rect_mm["x"] * scale_x))
    top = max(0, int(map_rect_mm["y"] * scale_y))
    right = min(image.width(), int((map_rect_mm["x"] + map_rect_mm["width"]) * scale_x))
    bottom = min(image.height(), int((map_rect_mm["y"] + map_rect_mm["height"]) * scale_y))
    if right - left < 8 or bottom - top < 8:
        return None

    # Amostragem em grade: percorrer milhões de pixels dentro do QGIS trava a
    # interface. ~140x140 amostras bastam para distinguir mapa de folha branca.
    steps = 140
    step_x = max(1, (right - left) // steps)
    step_y = max(1, (bottom - top) // steps)
    total = 0
    inked = 0
    for y in range(top, bottom, step_y):
        for x in range(left, right, step_x):
            total += 1
            pixel = image.pixel(x, y)
            red, green, blue = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF
            if red < 246 or green < 246 or blue < 246:
                inked += 1
    if total == 0:
        return None
    return inked / total
