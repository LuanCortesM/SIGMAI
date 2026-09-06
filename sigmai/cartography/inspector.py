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


#: Classes que a observação descreve mesmo sem id (páginas, molduras e
#: grupos ficam de fora: não são elementos cartográficos).
_TYPE_NAMES = {
    "QgsLayoutItemMap": "map",
    "QgsLayoutItemLegend": "legend",
    "QgsLayoutItemScaleBar": "scalebar",
    "QgsLayoutItemLabel": "label",
    "QgsLayoutItemPicture": "picture",
    "QgsLayoutItemShape": "shape",
}
_OBSERVABLE_WITHOUT_ID = frozenset(name for name in _TYPE_NAMES if name != "QgsLayoutItemShape")

#: Trechos de caminho que denunciam uma rosa dos ventos numa imagem.
_NORTH_PATH_HINTS = ("north", "norte", "arrow", "compass", "rosa", "bussola", "bússola")

#: Marcadores de procedência (espelham os do regulamento; a inferência só
#: precisa reconhecer o rótulo, o regulamento é quem julga o conteúdo).
_SOURCE_HINTS = ("fonte", "source", "dados:", "data source", "elabora", "autor", "author", "cartografia", "credit")


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
        "map_frames": [],
        "inset": None,
        "output": _observe_output(output_path),
    }

    map_item = None
    legend_item = None
    scalebar_item = None
    north_item = None
    inset_item = None

    # Itens sem id NÃO são descartados. O QGIS deixa o id vazio em tudo o que
    # o usuário cria pela interface, e scripts raramente o preenchem: pular
    # esses itens deixava a auditoria cega para qualquer layout que o SIGMAI
    # não tivesse composto — um mapa completo, feito à mão, recebia nota D
    # por "não ter título". O id passa a ser sintético e o papel é inferido
    # do tipo, do texto e da geometria (_infer_roles).
    pairs: list[tuple[Any, dict[str, Any]]] = []
    counters: dict[str, int] = {}
    for item in _safe(layout.items, []) or []:
        item_id = _safe(getattr(item, "id", lambda: ""), "") or ""
        class_name = type(item).__name__
        inferred_id = False
        if not item_id:
            if class_name not in _OBSERVABLE_WITHOUT_ID:
                continue
            counters[class_name] = counters.get(class_name, 0) + 1
            item_id = f"{_TYPE_NAMES.get(class_name, class_name)}#{counters[class_name]}"
            inferred_id = True
        entry = _observe_item(item, item_id)
        if inferred_id:
            entry["id_inferred"] = True
        pairs.append((item, entry))

    _infer_roles(pairs)

    for item, entry in pairs:
        item_id = entry["id"]
        observation["items"].append(entry)
        role = entry.get("role")
        if role == "map":
            observation["map_frames"].append({
                "item_id": item_id,
                "scale": round(float(_safe(item.scale, 0.0) or 0.0), 1),
                "visible_layer_names": _visible_layer_names(item),
                "label_only_layer_names": _label_only_layer_names(_safe(item.layers, []) or []),
            })
            # Num layout de comparação há dois itens de mapa; o laudo se refere
            # ao principal, identificado pelo id — ou, sem ids, ao maior quadro
            # (_infer_roles já rebaixou os menores a inserto).
            if map_item is None or item_id == "main_map":
                map_item = item
        elif role == "legend" and legend_item is None:
            legend_item = item
        elif role == "scalebar" and scalebar_item is None:
            scalebar_item = item
        elif role == "north" and north_item is None:
            north_item = item
        elif role == "inset" and inset_item is None:
            inset_item = item

    # O id que a observação carrega é o do inventário (sintético quando o
    # item não tem id): é por ele que o regulamento reconhece cada papel.
    ids = {id(item): entry["id"] for item, entry in pairs}

    if map_item is not None:
        observation["map"] = _observe_map(map_item, data_extent, ink_fraction)
        observation["map"]["item_id"] = ids.get(id(map_item), observation["map"]["item_id"])
    if inset_item is not None:
        observation["inset"] = _observe_inset(inset_item, map_item)
        observation["inset"]["item_id"] = ids.get(id(inset_item), observation["inset"]["item_id"])
    if legend_item is not None:
        observation["legend"] = _observe_legend(legend_item)
        observation["legend"]["item_id"] = ids.get(id(legend_item), observation["legend"]["item_id"])
    if scalebar_item is not None:
        observation["scalebar"] = _observe_scalebar(scalebar_item, map_item, observation["items"])
        observation["scalebar"]["item_id"] = ids.get(id(scalebar_item), observation["scalebar"]["item_id"])
    if north_item is not None:
        observation["north"] = _observe_north(north_item)
        observation["north"]["item_id"] = ids.get(id(north_item), observation["north"]["item_id"])

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

    if type_name == "picture":
        entry["picture_path"] = _safe(getattr(item, "picturePath", None), "") or ""
    if type_name == "map":
        try:
            entry["overviews"] = int(item.overviews().size())
        except Exception:
            entry["overviews"] = 0

    entry["role"] = _role_for(item_id, type_name, entry.get("text", ""), entry.get("picture_path", ""))
    return entry


def _role_for(item_id: str, type_name: str, text: str, picture_path: str = "") -> str:
    if item_id in ROLE_BY_ITEM_ID:
        return ROLE_BY_ITEM_ID[item_id]
    lowered = item_id.lower()
    for key, role in ROLE_BY_ITEM_ID.items():
        if key in lowered:
            return role
    if type_name in {"map", "legend", "scalebar"}:
        return {"map": "map", "legend": "legend", "scalebar": "scalebar"}[type_name]
    if type_name == "picture":
        haystack = lowered + " " + str(picture_path or "").lower()
        if any(hint in haystack for hint in _NORTH_PATH_HINTS):
            return "north"
    if type_name == "label" and "1:" in str(text):
        return "scale_text"
    return type_name


def _infer_roles(pairs: list[tuple[Any, dict[str, Any]]]) -> None:
    """Papéis para itens que o id não identifica.

    Só preenche o que está vago: um layout composto pelo SIGMAI, com ids
    explícitos, sai desta função intocado. Num layout feito à mão o título é
    o rótulo de maior corpo, o subtítulo é o rótulo logo abaixo dele, a linha
    de procedência é o rótulo que fala de fonte ou autoria, o quadro
    principal é o maior mapa e os demais quadros — menores, geralmente com um
    quadro-guia (overview) — são insertos. Cada papel inferido é marcado
    (``role_inferred``) para que o laudo possa dizer de onde veio.
    """
    entries = [entry for _, entry in pairs]
    roles = {entry.get("role") for entry in entries}

    maps = [entry for entry in entries if entry.get("role") == "map"]
    if len(maps) > 1 and not any(entry["id"] == "main_map" for entry in maps):
        inferable = [entry for entry in maps if entry.get("id_inferred")]
        if inferable:
            def area(entry: dict[str, Any]) -> float:
                return float(entry.get("width") or 0.0) * float(entry.get("height") or 0.0)

            main = max(maps, key=area)
            for entry in inferable:
                if entry is main:
                    continue
                if int(entry.get("overviews") or 0) > 0 or area(entry) < 0.5 * area(main):
                    entry["role"] = "inset"
                    entry["role_inferred"] = True

    labels = [
        entry for entry in entries
        if entry.get("type") == "label" and entry.get("role") == "label" and str(entry.get("text", "")).strip()
    ]

    if "source" not in roles:
        # Fonte pesa mais que autoria: "Mapa elaborado em QGIS" também fala em
        # elaboração, mas o bloco de procedência é o que cita a origem dos dados.
        def credit_score(entry: dict[str, Any]) -> tuple[int, int]:
            text = str(entry.get("text", "")).lower()
            source_hits = sum(2 for hint in _SOURCE_HINTS[:4] if hint in text)
            author_hits = sum(1 for hint in _SOURCE_HINTS[4:] if hint in text)
            return (source_hits + author_hits, len(text))

        scored = [entry for entry in labels if credit_score(entry)[0] > 0]
        if scored:
            best = max(scored, key=credit_score)
            best["role"] = "source"
            best["role_inferred"] = True
        labels = [entry for entry in labels if entry.get("role") == "label"]

    if "title" not in roles and labels:
        sized = [entry for entry in labels if float(entry.get("font_size_pt") or 0.0) > 0]
        if sized:
            title = max(sized, key=lambda entry: float(entry["font_size_pt"]))
            title["role"] = "title"
            title["role_inferred"] = True
            if "subtitle" not in roles:
                below = [
                    entry for entry in sized
                    if entry is not title
                    and float(entry.get("font_size_pt") or 0.0) < float(title["font_size_pt"])
                    and -float(title.get("height", 0.0)) / 2.0
                    <= float(entry.get("y", 0.0)) - (float(title.get("y", 0.0)) + float(title.get("height", 0.0)))
                    <= 12.0
                ]
                if below:
                    subtitle = min(below, key=lambda entry: float(entry.get("y", 0.0)))
                    subtitle["role"] = "subtitle"
                    subtitle["role_inferred"] = True


def _existing_grid(map_item: Any) -> Any:
    """Primeira grade já existente no quadro, ou None.

    ``QgsLayoutItemMap.grid()`` *cria* uma grade quando o quadro não tem
    nenhuma — habilitada e com intervalo zero. Observar um mapa sem grade por
    esse caminho fabricava uma grade-fantasma: o regulamento passava a acusar
    CART026/CART027 num mapa que o usuário pediu explicitamente sem grade, e
    CART010 aprovava uma grade que não existia. A leitura passa pela pilha
    (``grids()``), que não altera o layout inspecionado.
    """
    grids = getattr(map_item, "grids", None)
    stack = _safe(grids) if callable(grids) else None
    if stack is None:
        return None
    try:
        if int(stack.size()) <= 0:
            return None
        return stack.grid(0)
    except Exception:
        return None


def _observe_map(map_item: Any, data_extent: dict[str, float] | None, ink_fraction: float | None) -> dict[str, Any]:
    crs = _safe(map_item.crs)
    layers = _safe(map_item.layers, []) or []
    grid = _existing_grid(map_item)

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
        "label_only_layer_names": _label_only_layer_names(layers),
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


def _observe_inset(inset_item: Any, main_map: Any) -> dict[str, Any]:
    """O inserto de localização: extensão, escala, camadas e quanto de cada
    camada de contexto cabe nele.

    A auditoria não olhava o inserto: um localizador que corta o estado ao
    meio passava com nota A porque a observação só descrevia o quadro
    principal. ``layer_coverage`` é a fração da extensão de cada camada que
    está dentro do inserto — 1,0 quando o estado inteiro aparece.
    """
    crs = _safe(inset_item.crs)
    layers = _safe(inset_item.layers, []) or []
    extent = _safe(inset_item.extent)
    info: dict[str, Any] = {
        "item_id": _safe(inset_item.id, "") or "",
        "crs": _safe(crs.authid, "") if crs is not None else "",
        "scale": round(float(_safe(inset_item.scale, 0.0) or 0.0), 1),
        "extent": _rect_dict(extent),
        "visible_layer_names": [str(_safe(layer.name, "")) for layer in layers],
        "layer_coverage": {},
        "shows_main_frame": False,
    }
    try:
        from qgis.core import QgsCoordinateTransform, QgsProject  # type: ignore

        for layer in layers:
            layer_extent = layer.extent()
            if layer_extent is None or layer_extent.isEmpty() or crs is None:
                continue
            if layer.crs().isValid() and crs.isValid() and layer.crs().authid() != crs.authid():
                layer_extent = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance()).transformBoundingBox(layer_extent)
            shown = layer_extent.intersect(extent)
            area = layer_extent.width() * layer_extent.height()
            info["layer_coverage"][str(layer.name())] = round((shown.width() * shown.height()) / area, 3) if area > 0 else 1.0
        if main_map is not None and extent is not None:
            main_extent = _safe(main_map.extent)
            if main_extent is not None:
                info["shows_main_frame"] = bool(extent.contains(main_extent))
    except Exception:
        pass
    try:
        info["overviews"] = int(inset_item.overviews().size())
    except Exception:
        info["overviews"] = None
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


def _label_only_layer_names(layers: Any) -> list[str]:
    """Camadas que não desenham símbolo nenhum (``QgsNullSymbolRenderer``).

    São camadas de apoio usadas só para posicionar rótulos — nome de estado,
    nome da UC fora do polígono. Não há o que explicar na legenda: exigir uma
    entrada para elas acusava de incompleta uma legenda correta.
    """
    names: list[str] = []
    for layer in layers or []:
        try:
            renderer = layer.renderer()
            if renderer is not None and str(renderer.type()) == "nullSymbol":
                names.append(str(layer.name()))
        except Exception:
            continue
    return names


def _visible_layer_names(map_item: Any) -> list[str]:
    """Nomes das camadas que este quadro desenha.

    Num layout de comparação cada quadro tem a sua própria lista, e a legenda
    responde pelos dois: avaliar só a do quadro principal acusava de fantasma
    uma camada que aparece, bem visível, no segundo painel.
    """
    try:
        layers = map_item.layers() or []
        if not layers:
            project = map_item.layout().project() if hasattr(map_item, "layout") else None
            layers = list(project.mapLayers().values()) if project is not None else []
        return [str(layer.name()) for layer in layers]
    except Exception:
        return []


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
    opaque = 0
    seen: set[int] = set()
    for y in range(top, bottom, step_y):
        for x in range(left, right, step_x):
            total += 1
            pixel = image.pixel(x, y)
            alpha = (pixel >> 24) & 0xFF
            red, green, blue = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF
            seen.add(pixel)
            if alpha < 8:
                # Pixel transparente não é tinta. Sem esta verificação, uma
                # exportação que não desenhou nada — todos os pixels em
                # (0,0,0,0) — era contada como 100% de tinta e passava na regra
                # de quadro em branco. Foi assim que um mapa inteiramente vazio
                # recebeu nota A: o arquivo tinha o tamanho certo, o código de
                # retorno dizia sucesso, e a única checagem visual olhava só o
                # RGB.
                continue
            opaque += 1
            if red < 246 or green < 246 or blue < 246:
                inked += 1
    if total == 0:
        return None
    if opaque == 0:
        return 0.0  # nada opaco foi desenhado: o quadro está vazio
    if len(seen) <= 1:
        return 0.0  # cor única em todo o quadro: nada foi renderizado
    return inked / total
