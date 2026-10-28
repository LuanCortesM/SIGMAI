"""Lê um layout do QGIS e produz a *observação* que o regulamento avalia.

Separar a leitura da avaliação tem duas consequências práticas: o regulamento
pode ser testado sem QGIS, e o laudo passa a ser reproduzível — a mesma
observação sempre gera o mesmo laudo, o que permite guardar observações como
casos de teste de regressão cartográfica.
"""

from __future__ import annotations

import math

from pathlib import Path
from typing import Any

from .pagespec import PageSpec
from .rulebook import AREA_OF_USE_MARGIN_DEGREES, HEATMAP_VISIBLE_MIN, NODATA_SENTINELS

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
    ink_grid: list[list[float]] | None = None,
    label_results: dict[str, dict[str, Any]] | None = None,
    print_width_mm: float | None = None,
    subject_layer_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Descreve um ``QgsPrintLayout`` como dicionário puro.

    ``ink_grid`` é a tinta do quadro principal medida numa grade (ver
    ``measure_ink_grid``); ``label_results`` é o que ``collect_label_results``
    devolveu para cada quadro, indexado pelo id do item; ``print_width_mm`` é
    a largura em que a figura vai ser impressa quando se sabe (coluna de
    revista) — o regulamento reavalia as fontes nessa largura.
    """
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
        "print_width_mm": float(print_width_mm) if print_width_mm else None,
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

    map_frames: list[tuple[Any, str]] = []
    for item, entry in pairs:
        item_id = entry["id"]
        observation["items"].append(entry)
        role = entry.get("role")
        if role == "map":
            frame_entry = {
                "item_id": item_id,
                "scale": round(float(_safe(item.scale, 0.0) or 0.0), 1),
                "visible_layer_names": _visible_layer_names(item),
                "label_only_layer_names": _label_only_layer_names(_safe(item.layers, []) or []),
                "value_scales": _value_scales(item),
            }
            if label_results and item_id in label_results:
                frame_entry["labels"] = label_results[item_id]
            observation["map_frames"].append(frame_entry)
            map_frames.append((item, item_id))
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
        observation["map"] = _observe_map(map_item, data_extent, ink_fraction, subject_layer_ids)
        observation["map"]["item_id"] = ids.get(id(map_item), observation["map"]["item_id"])
        observation["map"]["rendered_ink_grid"] = ink_grid
        if label_results and observation["map"]["item_id"] in label_results:
            observation["map"]["labels"] = label_results[observation["map"]["item_id"]]
        # Os outros painéis de uma comparação também são mapas: pontos
        # amontoados, rampa e mapa de calor de cada um entram no laudo. Antes, a
        # CART076 só media o primeiro painel, e o painel B passava sem medida.
        for item, frame_id in map_frames:
            if item is map_item:
                continue
            _merge_frame_measures(observation["map"], item, frame_id)
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


def _observe_map(
    map_item: Any, data_extent: dict[str, float] | None, ink_fraction: float | None,
    subject_layer_ids: list[str] | None = None,
) -> dict[str, Any]:
    crs = _safe(map_item.crs)
    layers = _safe(map_item.layers, []) or []
    grid = _existing_grid(map_item)
    stack = measure_layer_stack(map_item, layers)
    layer_ink = stack["ink_fraction"] if stack is not None else measure_layer_ink(map_item, layers)
    # O assunto do mapa tem de estar à vista (CART075). Mede-se a menos
    # visível das camadas de assunto que o quadro desenha.
    subject_visible = None
    if stack is not None and subject_layer_ids:
        measured = [stack["visible_by_id"][layer_id] for layer_id in subject_layer_ids if layer_id in stack["visible_by_id"]]
        subject_visible = min(measured) if measured else None

    info: dict[str, Any] = {
        "item_id": _safe(map_item.id, "") or "",
        # Uma projeção criada de uma cadeia PROJ (a LAEA centrada do
        # compositor) não tem código nem nome: sem a cadeia, CART008 não a via.
        "crs": (_safe(crs.authid, "") or _safe(crs.description, "") or _safe(crs.toProj, "")) if crs is not None else "",
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
        "layer_ink_fraction": layer_ink,
        **_visibility_entries(stack),
        "subject_layer_ids": list(subject_layer_ids or []),
        "subject_visible_fraction": subject_visible,
        "layer_colours": _layer_colours(layers),
        "point_stacking": _point_stacking(map_item, layers),
        "raster_ramps": _raster_ramps(map_item, layers),
        "coordinate_checks": _coordinate_checks(map_item, layers),
        "extent_outliers": _extent_outliers(map_item, layers),
        "heatmap_visibility": _heatmap_visibility(map_item, layers),
        "polygon_coverage": _polygon_coverage(map_item, layers),
        "data_ink_grid": stack.get("ink_grid") if stack is not None else None,
    }

    if grid is not None:
        info["grid"] = {
            "enabled": bool(_safe(grid.enabled, False)),
            "interval_x": float(_safe(grid.intervalX, 0.0) or 0.0),
            "interval_y": float(_safe(grid.intervalY, 0.0) or 0.0),
            "annotations": bool(_safe(grid.annotationEnabled, False)),
            # Grade em graus sobre um mapa projetado (map_crs="auto" num
            # continente ou no mundo): os meridianos mostram o norte.
            "graticule": bool(_graticule_over_projection(grid, crs)),
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
    observation = {
        "item_id": _safe(legend_item.id, "") or "",
        "title": _safe(legend_item.title, "") or "",
        "layer_names": names,
        "auto_update": bool(_safe(legend_item.autoUpdateModel, True)),
        "column_count": int(_safe(legend_item.columnCount, 1) or 1),
    }
    # Caixa × conteúdo (CART072): QgsLayoutItemLegend corta na borda o que
    # não cabe, sem avisar. QgsLegendRenderer.minimumSize diz o tamanho que
    # o conteúdo precisa; com resizeToContents a caixa cresce sozinha.
    try:
        from qgis.core import QgsLegendRenderer  # type: ignore

        size = legend_item.sizeWithUnits()
        observation["box_mm"] = {"width": round(float(size.width()), 2), "height": round(float(size.height()), 2)}
        observation["resize_to_contents"] = bool(legend_item.resizeToContents())
        needed = QgsLegendRenderer(legend_item.model(), legend_item.legendSettings()).minimumSize()
        observation["content_mm"] = {"width": round(float(needed.width()), 2), "height": round(float(needed.height()), 2)}
    except Exception:
        pass
    return observation


def _label_only_layer_names(layers: Any) -> list[str]:
    """Camadas de apoio sem nada a explicar na legenda.

    As que não desenham símbolo nenhum (``QgsNullSymbolRenderer``), usadas
    só para posicionar rótulos — nome de estado, nome da UC fora do
    polígono —, o relevo sombreado, que é efeito visual sobre outra camada
    e não tem classes nem rampa, e o mapa de base (XYZ, WMS). Exigir uma
    entrada para elas acusava de incompleta uma legenda correta.
    """
    names: list[str] = []
    for layer in layers or []:
        try:
            renderer = layer.renderer()
            if renderer is not None and str(renderer.type()) in ("nullSymbol", "hillshade"):
                names.append(str(layer.name()))
            elif not hasattr(layer, "geometryType") and layer.providerType() in ("wms", "arcgismapserver"):
                names.append(str(layer.name()))  # mapa de base: fundo, creditado na linha de fonte
        except Exception:
            continue
    return names


def _symbol_appearance(symbol: Any, family: str) -> tuple[str, str]:
    """Família e cor que o leitor de fato vê num símbolo.

    Polígono sem preenchimento é um traço: compete com as linhas, pela cor do
    contorno — o contorno destacado do estado entrava como "preenchimento
    branco" e reprovava CART070 contra o azul quase branco do contexto.
    Hachuras de padrões diferentes se distinguem pelo padrão, não pela cor:
    cada padrão é uma família à parte.
    """
    colour = symbol.color().name()
    if family != "polygon":
        return family, colour
    try:
        from qgis.PyQt.QtCore import Qt  # type: ignore

        from .qtcompat import qt_enum

        first = symbol.symbolLayer(0)
        brush = first.brushStyle() if hasattr(first, "brushStyle") else None
        if brush is None:
            return family, colour
        if brush == qt_enum(Qt, "BrushStyle", "NoBrush"):
            stroke = first.strokeColor() if hasattr(first, "strokeColor") else symbol.color()
            return "line", stroke.name()
        if brush != qt_enum(Qt, "BrushStyle", "SolidPattern"):
            return f"polygon/{getattr(brush, 'name', int(brush) if isinstance(brush, int) else str(brush))}", colour
    except Exception:
        pass
    return family, colour


#: Fator de cada unidade de símbolo para milímetros no papel (CART076).
_SIZE_UNIT_MM = {"Millimeters": 1.0, "Points": 25.4 / 72.0, "Pixels": 25.4 / 96.0, "Inches": 25.4}
#: Valor numérico de cada unidade, igual no QGIS 3 (QgsUnitTypes.RenderUnit) e
#: no 4 (Qgis.RenderUnit). No 4, str() da unidade dá "0", não o nome.
_SIZE_UNIT_BY_VALUE = {0: "Millimeters", 1: "MapUnits", 2: "Pixels", 3: "Percentage", 4: "Points", 5: "Inches"}


def _marker_size_mm(symbol: Any, scale: float, map_units_metres: bool) -> float | None:
    """Diâmetro do símbolo de ponto no papel, em mm; None se varia por feição ou a unidade não se converte."""
    try:
        if symbol.dataDefinedSize().isActive():
            return None  # tamanho por feição: ver _proportional_min_size_mm
    except Exception:
        pass
    try:
        return _size_mm(float(symbol.size()), symbol.sizeUnit(), scale, map_units_metres)
    except Exception:
        return None


def _proportional_min_size_mm(symbol: Any, scale: float, map_units_metres: bool) -> float | None:
    """Menor círculo de um símbolo proporcional (tamanho por campo, com transformador), em mm; senão None."""
    try:
        size = symbol.dataDefinedSize()
        if not size.isActive():
            return None
        transformer = size.transformer()
        minimum = float(transformer.minSize()) if transformer is not None and hasattr(transformer, "minSize") else 0.0
        if not minimum > 0:
            return None
        return _size_mm(minimum, symbol.sizeUnit(), scale, map_units_metres)
    except Exception:
        return None


def _size_mm(size: float, raw_unit: Any, scale: float, map_units_metres: bool) -> float | None:
    """Um tamanho de símbolo na unidade ``raw_unit`` levado a mm no papel; None se não se converte."""
    try:
        unit = getattr(raw_unit, "name", None) or _SIZE_UNIT_BY_VALUE.get(int(raw_unit), str(raw_unit))
    except Exception:
        return None
    for name, factor in _SIZE_UNIT_MM.items():
        if name in unit:
            return size * factor
    if "MapUnit" in unit and map_units_metres and scale > 0:
        return size / scale * 1000.0
    return None


def _graticule_over_projection(grid: Any, map_crs: Any) -> bool:
    try:
        grid_crs = grid.crs()
        return bool(grid_crs.isValid() and grid_crs.isGeographic() and map_crs is not None and not map_crs.isGeographic())
    except Exception:
        return False


def _sites_of(layer: Any) -> str:
    """Id da camada de registros de que count_points_by_site tirou estes locais, ou ""."""
    try:
        from ..qgis_actions.gis_tools import SITES_OF_PROPERTY

        return str(layer.customProperty(SITES_OF_PROPERTY, "") or "")
    except Exception:
        return ""


def _merge_frame_measures(main: dict[str, Any], item: Any, frame_id: str) -> None:
    """Junta às medidas do quadro principal as de outro painel, cada entrada marcada com o quadro."""
    layers = _safe(item.layers, []) or []
    measures = {"point_stacking": _point_stacking, "raster_ramps": _raster_ramps,
                "heatmap_visibility": _heatmap_visibility}
    for key, measure in measures.items():
        extra = measure(item, layers)
        if not extra:
            continue
        for entry in extra:
            entry["frame"] = frame_id
        main[key] = list(main.get(key) or []) + list(extra)


def _point_stacking(map_item: Any, layers: Any) -> list[dict[str, Any]] | None:
    """Quantos pontos de cada camada de pontos o quadro deixa de mostrar (CART076).

    Camadas desenhadas com símbolos de tamanho fixo (único, categorizado,
    graduado) e com símbolo proporcional (único, com o tamanho por campo): o
    círculo proporcional mostra quantos há em cada local, mas só se os locais
    não caírem uns sobre os outros. Mapa de calor e agrupamento mostram a
    contagem de outro jeito e ficam de fora. Os pontos dentro da extensão do
    quadro são levados para mm do quadro e medidos por ``pointdensity.stacking``
    com o menor símbolo e a menor opacidade da camada — a leitura mais
    favorável ao mapa.
    """
    try:
        from qgis.core import QgsProject  # type: ignore

        from .pointdensity import stacking

        crs = map_item.crs()
        if not crs.isValid():
            crs = QgsProject.instance().crs()
        scale = float(map_item.scale())
        metres = "Meters" in str(crs.mapUnits())
        out: list[dict[str, Any]] = []
        for layer in _frame_layers(map_item, layers):
            try:
                if int(layer.geometryType()) != 0:
                    continue
                renderer = layer.renderer()
                rtype = str(renderer.type()) if renderer is not None else ""
            except Exception:
                continue
            items: list[Any] = []  # cópias donas dos símbolos: vivas enquanto forem lidos (ver _layer_colours)
            if rtype == "singleSymbol":
                symbols = [renderer.symbol()] if renderer.symbol() is not None else []
            elif rtype == "categorizedSymbol":
                items = list(renderer.categories())
                symbols = [c.symbol() for c in items if c.symbol() is not None and c.renderState()]
            elif rtype == "graduatedSymbol":
                items = list(renderer.ranges())
                symbols = [r.symbol() for r in items if r.symbol() is not None and r.renderState()]
            else:
                continue
            sizes = [_marker_size_mm(symbol, scale, metres) for symbol in symbols]
            proportional = rtype == "singleSymbol" and len(symbols) == 1 and sizes == [None]
            if proportional:
                sizes = [_proportional_min_size_mm(symbols[0], scale, metres)]
            if not sizes or any(size is None or size <= 0 for size in sizes):
                continue
            opacities = []
            for symbol in symbols:
                try:
                    opacities.append(float(symbol.opacity()) * float(symbol.color().alphaF()))
                except Exception:
                    opacities.append(1.0)
            opacity = min(opacities) * float(_safe(layer.opacity, 1.0) or 1.0)
            points = frame_points_mm(map_item, layer)
            if points is None:
                continue
            found = stacking(points, min(sizes), opacity)
            entry = {"layer": str(layer.name()), "layer_id": str(layer.id()),
                     "symbol_mm": round(min(sizes), 2), "opacity": round(opacity, 2), **found}
            if proportional:
                entry.update(proportional=True, scale=int(round(scale)) if scale > 0 else None,
                             source_layer_id=_sites_of(layer))
            out.append(entry)
        return out
    except Exception:
        return None


def frame_points_mm(map_item: Any, layer: Any) -> list[tuple[float, float]] | None:
    """Os pontos da camada dentro da extensão do quadro, em mm a partir do canto superior esquerdo."""
    try:
        from qgis.core import QgsCoordinateTransform, QgsFeatureRequest, QgsProject  # type: ignore

        extent = map_item.extent()
        width_mm, height_mm = float(map_item.rect().width()), float(map_item.rect().height())
        if extent.width() <= 0 or extent.height() <= 0 or width_mm <= 0 or height_mm <= 0:
            return None
        crs = map_item.crs()
        if not crs.isValid():
            crs = QgsProject.instance().crs()
        transform = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
        try:
            request_rect = transform.transformBoundingBox(extent, _reverse_direction())
            request = QgsFeatureRequest().setFilterRect(request_rect).setNoAttributes()
        except Exception:
            request = QgsFeatureRequest().setNoAttributes()
        x0, y1 = extent.xMinimum(), extent.yMaximum()
        sx, sy = width_mm / extent.width(), height_mm / extent.height()
        points: list[tuple[float, float]] = []
        for feature in layer.getFeatures(request):
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            parts = geometry.asMultiPoint() if geometry.isMultipart() else [geometry.asPoint()]
            for part in parts:
                p = transform.transform(part)
                if extent.contains(p):
                    points.append(((p.x() - x0) * sx, (y1 - p.y()) * sy))
        return points
    except Exception:
        return None


def _reverse_direction() -> Any:
    from qgis.core import Qgis  # type: ignore

    from .qtcompat import qt_enum

    return qt_enum(Qgis, "TransformDirection", "Reverse")


def _raster_ramps(map_item: Any, layers: Any) -> list[dict[str, Any]] | None:
    """Quanto da rampa de cores de cada raster os pixels do quadro usam (CART077).

    Só rampas contínuas (pseudocor interpolada) e cinza esticado: em classes
    os limites são escolha de quem classificou. Os pixels do quadro (até
    200 × 200, sem os "sem dado" do arquivo nem os do usuário) dão os
    percentis 2 e 98; a fração usada é a amplitude entre eles sobre a da
    rampa. Um -32.768 não declarado esticava a rampa e deixava 7 % dela em uso;
    os valores de preenchimento de ``NODATA_SENTINELS`` ficam fora dos
    percentis, senão a própria sobra parecia usar a rampa.
    """
    try:
        from qgis.core import QgsCoordinateTransform, QgsProject  # type: ignore

        out: list[dict[str, Any]] = []
        for layer in _frame_layers(map_item, layers):
            if hasattr(layer, "geometryType"):
                continue
            renderer = _safe(layer.renderer)
            kind = str(_safe(renderer.type, "")) if renderer is not None else ""
            if kind == "singlebandpseudocolor":
                shader = renderer.shader().rasterShaderFunction()
                if int(shader.colorRampType()) != 0:  # 0 = interpolada nas duas versões do QGIS
                    continue
                low, high = float(renderer.classificationMin()), float(renderer.classificationMax())
                band = int(renderer.band() if hasattr(renderer, "band") else renderer.inputBand())
            elif kind == "singlebandgray":
                enhancement = renderer.contrastEnhancement()
                if enhancement is None:
                    continue
                low, high = float(enhancement.minimumValue()), float(enhancement.maximumValue())
                band = int(renderer.inputBand() if hasattr(renderer, "inputBand") else renderer.grayBand())
            else:
                continue
            if not (high > low):
                continue
            provider = layer.dataProvider()
            transform = QgsCoordinateTransform(map_item.crs(), layer.crs(), QgsProject.instance())
            rect = transform.transformBoundingBox(map_item.extent()).intersect(layer.extent())
            if rect.isEmpty():
                continue
            block = provider.block(band, rect, 200, 200)
            ranges = list(_safe(lambda: provider.userNoDataValues(band), []) or [])
            values: list[float] = []
            for row in range(block.height()):
                for col in range(block.width()):
                    if block.isNoData(row, col):
                        continue
                    value = float(block.value(row, col))
                    if (not math.isfinite(value) or any(r.contains(value) for r in ranges)
                            or value in NODATA_SENTINELS):
                        continue
                    values.append(value)
            if len(values) < 50:
                continue
            values.sort()
            p02 = values[int(0.02 * (len(values) - 1))]
            p98 = values[int(0.98 * (len(values) - 1))]
            out.append({"layer": str(layer.name()), "renderer": kind, "ramp_min": low, "ramp_max": high,
                        "p02": p02, "p98": p98, "data_min": values[0], "data_max": values[-1],
                        "used_fraction": round(max(0.0, min(1.0, (p98 - p02) / (high - low))), 4)})
        return out
    except Exception:
        return None


def _wgs84_points(layer: Any, limit: int = 2_000_000) -> list[tuple[float, float]] | None:
    """Os vértices de ponto da camada em graus (WGS 84); None se a camada não é de pontos ou é grande demais."""
    try:
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest, QgsProject  # type: ignore

        if int(layer.geometryType()) != 0 or int(layer.featureCount()) > limit:
            return None
        transform = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
        out: list[tuple[float, float]] = []
        for feature in layer.getFeatures(QgsFeatureRequest().setNoAttributes()):
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            for part in (geometry.asMultiPoint() if geometry.isMultipart() else [geometry.asPoint()]):
                try:
                    q = transform.transform(part)
                    out.append((q.x(), q.y()))
                except Exception:
                    out.append((float("nan"), float("nan")))
        return out
    except Exception:
        return None


def _coordinate_checks(map_item: Any, layers: Any) -> list[dict[str, Any]] | None:
    """Coordenadas que não podem estar certas (CART078).

    Para cada camada vetorial do quadro: quantas feições caem fora da área de
    uso do seu sistema de referência (com ``AREA_OF_USE_MARGIN_DEGREES`` de
    folga), se uma camada em sistema projetado tem só números de graus (lat/lon
    declarados como UTM), e quantos pontos estão em 0,0 — a "ilha nula", o
    valor que planilhas e bancos gravam quando falta a coordenada.
    """
    try:
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject  # type: ignore

        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        out: list[dict[str, Any]] = []
        for layer in _frame_layers(map_item, layers):
            if not hasattr(layer, "geometryType") or _is_label_only_layer(layer):
                continue
            crs = layer.crs()
            if not crs.isValid():
                continue
            extent = layer.extent()
            if extent is None or extent.isNull():
                continue
            entry: dict[str, Any] = {"layer": str(layer.name()), "crs": crs.authid() or crs.description(),
                                     "features": int(_safe(layer.featureCount, 0) or 0)}
            entry["degree_like"] = bool(
                not crs.isGeographic() and -180.0 <= extent.xMinimum() and extent.xMaximum() <= 180.0
                and -90.0 <= extent.yMinimum() and extent.yMaximum() <= 90.0)
            bounds = _safe(crs.bounds)
            usable = bounds is not None and not bounds.isEmpty() and not (bounds.width() >= 359.0 and bounds.height() >= 179.0)
            if usable:
                margin = AREA_OF_USE_MARGIN_DEGREES
                w, s, e, n = (bounds.xMinimum() - margin, bounds.yMinimum() - margin,
                              bounds.xMaximum() + margin, bounds.yMaximum() + margin)
                entry["area_of_use"] = [round(bounds.xMinimum(), 2), round(bounds.yMinimum(), 2),
                                        round(bounds.xMaximum(), 2), round(bounds.yMaximum(), 2)]
            points = _wgs84_points(layer)
            if points is not None:
                entry["null_island"] = sum(1 for x, y in points if abs(x) < 1e-6 and abs(y) < 1e-6)
                if usable:
                    outside = [(x, y) for x, y in points if not (w <= x <= e and s <= y <= n)]
                    entry["outside_area_of_use"] = len(outside)
                    entry["outside_examples"] = [[round(x, 4), round(y, 4)] for x, y in outside[:3]]
            elif usable:
                try:
                    box = QgsCoordinateTransform(crs, wgs84, QgsProject.instance()).transformBoundingBox(extent)
                    inside = not (box.xMaximum() < w or box.xMinimum() > e or box.yMaximum() < s or box.yMinimum() > n)
                except Exception:
                    inside = False
                entry["outside_area_of_use"] = 0 if inside else entry["features"]
            out.append(entry)
        return out
    except Exception:
        return None


def _extent_outliers(map_item: Any, layers: Any) -> list[dict[str, Any]] | None:
    """Pontos isolados que abrem o recorte (CART079).

    Para cada camada de pontos com 20 pontos ou mais: a caixa dos percentis 1
    e 99, em x e em y, é o núcleo dos dados; pontos fora dela, com folga de
    metade do seu tamanho, são isolados. Medido no sistema do quadro.
    """
    try:
        from qgis.core import QgsCoordinateTransform, QgsFeatureRequest, QgsProject  # type: ignore

        out: list[dict[str, Any]] = []
        for layer in _frame_layers(map_item, layers):
            if not hasattr(layer, "geometryType") or int(layer.geometryType()) != 0:
                continue
            if int(_safe(layer.featureCount, 0) or 0) > 2_000_000:
                continue
            transform = QgsCoordinateTransform(layer.crs(), map_item.crs(), QgsProject.instance())
            xs: list[float] = []
            ys: list[float] = []
            for feature in layer.getFeatures(QgsFeatureRequest().setNoAttributes()):
                geometry = feature.geometry()
                if geometry is None or geometry.isEmpty():
                    continue
                for part in (geometry.asMultiPoint() if geometry.isMultipart() else [geometry.asPoint()]):
                    try:
                        q = transform.transform(part)
                    except Exception:
                        continue
                    if math.isfinite(q.x()) and math.isfinite(q.y()):
                        xs.append(q.x())
                        ys.append(q.y())
            if len(xs) < 20:
                continue
            sx, sy = sorted(xs), sorted(ys)
            n = len(xs)
            x1, x99 = sx[int(0.01 * (n - 1))], sx[int(0.99 * (n - 1))]
            y1, y99 = sy[int(0.01 * (n - 1))], sy[int(0.99 * (n - 1))]
            pad_x, pad_y = max((x99 - x1) * 0.5, 1e-9), max((y99 - y1) * 0.5, 1e-9)
            core = math.hypot(x99 - x1, y99 - y1)
            full = math.hypot(sx[-1] - sx[0], sy[-1] - sy[0])
            isolated = [(x, y) for x, y in zip(xs, ys)
                        if not (x1 - pad_x <= x <= x99 + pad_x and y1 - pad_y <= y <= y99 + pad_y)]
            out.append({"layer": str(layer.name()), "points": n, "isolated": len(isolated),
                        "core_diagonal": core, "full_diagonal": full,
                        "spread_ratio": round(full / core, 2) if core > 0 else None,
                        "units": str(_safe(lambda: map_item.crs().mapUnits(), "")).split(".")[-1]})
        return out
    except Exception:
        return None


def _heatmap_visibility(map_item: Any, layers: Any) -> list[dict[str, Any]] | None:
    """Que fração dos lugares com pontos o mapa de calor de fato mostra (CART080).

    Os pontos do quadro, em mm, são contados em células do tamanho do raio;
    a contagem da célula é a densidade local. Uma célula com pontos e menos
    de ``HEATMAP_VISIBLE_MIN`` do máximo (o da camada, se fixado, senão o da
    célula mais cheia) quase não pinta. Com um foco de 20.000 registros, os
    300 espalhados pelo parque sumiam e o mapa tirava nota A.
    """
    try:
        out: list[dict[str, Any]] = []
        for layer in _frame_layers(map_item, layers):
            renderer = _safe(layer.renderer) if hasattr(layer, "renderer") else None
            if renderer is None or str(_safe(renderer.type, "")) != "heatmapRenderer":
                continue
            radius = float(renderer.radius())
            unit = int(_safe(renderer.radiusUnit, 0) or 0)
            if unit == 1:  # unidades do mapa
                radius = radius / float(map_item.scale()) * 1000.0
            elif unit == 2:  # pixels a 96 dpi
                radius = radius * 25.4 / 96.0
            radius = max(radius, 0.2)
            points = frame_points_mm(map_item, layer)
            if not points:
                continue
            cells: dict[tuple[int, int], int] = {}
            for x, y in points:
                key = (int(x // radius), int(y // radius))
                cells[key] = cells.get(key, 0) + 1
            fixed = float(_safe(renderer.maximumValue, 0.0) or 0.0)
            peak = fixed if fixed > 0 else float(max(cells.values()))
            faint = [count for count in cells.values() if count < HEATMAP_VISIBLE_MIN * peak]
            out.append({"layer": str(layer.name()), "radius_mm": round(radius, 2), "places": len(cells),
                        "faint_places": len(faint), "faint_points": sum(faint), "points": len(points),
                        "peak": peak, "max_value_fixed": fixed > 0})
        return out
    except Exception:
        return None


def _layer_colours(layers: Any) -> list[dict[str, Any]]:
    """Cores que cada camada visível de fato desenha — uma por classe.

    Alimenta CART070 (daltonismo). Símbolo único: a cor do símbolo;
    categorizado/graduado: a cor de cada classe, com o rótulo da classe.
    ``family`` separa preenchimentos de polígono, traços de linha e pontos:
    só cores da mesma família competem entre si na leitura. Cada classe
    leva a sua família, porque contorno e hachura mudam a família.
    """
    out: list[dict[str, Any]] = []
    for layer in layers or []:
        try:
            renderer = layer.renderer()
            if renderer is None or str(renderer.type()) == "nullSymbol":
                continue
            geometry = int(layer.geometryType())
            family = {0: "point", 1: "line", 2: "polygon"}.get(geometry, "other")
            symbols: list[tuple[str, Any]] = []
            rtype = str(renderer.type())
            # categories()/ranges() devolvem CÓPIAS, donas dos seus símbolos:
            # a lista tem de viver enquanto os símbolos forem lidos. Numa
            # compreensão sobre a chamada direta ela morria antes, e ler a cor
            # de um símbolo já liberado derrubava o QGIS.
            items: list[Any] = []
            if rtype == "singleSymbol":
                if renderer.symbol() is not None:
                    symbols.append((str(layer.name()), renderer.symbol()))
            elif rtype == "categorizedSymbol":
                items = list(renderer.categories())
                symbols = [(str(c.label()), c.symbol()) for c in items if c.symbol() is not None and c.renderState()]
            elif rtype == "graduatedSymbol":
                items = list(renderer.ranges())
                symbols = [(str(r.label()), r.symbol()) for r in items if r.symbol() is not None and r.renderState()]
            else:
                continue
            by_family: dict[str, list[dict[str, str]]] = {}
            for label, symbol in symbols:
                klass_family, colour = _symbol_appearance(symbol, family)
                by_family.setdefault(klass_family, []).append({"label": label, "colour": colour})
            for klass_family, classes in by_family.items():
                out.append({"layer": str(layer.name()), "family": klass_family, "classes": classes})
        except Exception:
            continue
    return out


#: Feições por camada acima das quais a cobertura não é calculada — a
#: união de geometrias é O(n log n) e um cadastro de 200 mil lotes travaria
#: o QGIS do usuário durante a auditoria.
COVERAGE_MAX_FEATURES = 5000


def _polygon_coverage(map_item: Any, layers: Any) -> dict[str, Any] | None:
    """Fração do quadro coberta por dados de área (polígonos visíveis).

    É a medida de "quadro vazio" que não depende de renderização: pixels
    contam grade e rótulos como tinta, geometria não. Um mapa cuja metade
    leste não tem polígono nenhum tem cobertura ~0,45 mesmo que a grade
    cruze o vazio inteiro. ``None`` quando não há camada de polígonos ou o
    cálculo não é seguro (camada grande demais, CRS inválido).
    """
    try:
        from qgis.core import Qgis, QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry, QgsProject  # type: ignore

        from .qtcompat import qt_enum

        reverse = qt_enum(Qgis, "TransformDirection", "Reverse")
    except Exception:
        return None
    try:
        extent = map_item.extent()
        crs = map_item.crs()
        if extent is None or extent.isEmpty() or crs is None or not crs.isValid():
            return None
        frame_geometry = QgsGeometry.fromRect(extent)
        frame_area = float(extent.width() * extent.height())
        if frame_area <= 0:
            return None
        pieces: list[Any] = []
        per_layer: list[dict[str, Any]] = []
        polygon_layers = 0
        for layer in layers or []:
            if not hasattr(layer, "geometryType"):
                # Raster temático (elevação, cobertura da terra): a extensão
                # dele é dado de área tanto quanto um polígono. Mapa de base
                # (XYZ, WMS) não conta — ele forra qualquer quadro.
                try:
                    if layer.providerType() in ("wms", "arcgismapserver") or str(layer.renderer().type()) == "hillshade":
                        continue
                    footprint = QgsGeometry.fromRect(layer.extent())
                    if layer.crs().isValid() and layer.crs().authid() != crs.authid():
                        footprint = QgsGeometry.fromRect(QgsCoordinateTransform(
                            layer.crs(), crs, QgsProject.instance()).transformBoundingBox(layer.extent()))
                    clipped = footprint.intersection(frame_geometry)
                    polygon_layers += 1
                    if clipped is not None and not clipped.isEmpty():
                        pieces.append(clipped)
                        per_layer.append({"layer": str(layer.name()), "fraction": round(float(clipped.area()) / frame_area, 3),
                                          "raster": True})
                except Exception:
                    pass
                continue
            try:
                if int(layer.geometryType()) != 2:
                    continue
                renderer = layer.renderer()
                if renderer is not None and str(renderer.type()) == "nullSymbol":
                    continue
                polygon_layers += 1
                if layer.featureCount() > COVERAGE_MAX_FEATURES:
                    per_layer.append({"layer": str(layer.name()), "skipped": "camada grande demais"})
                    continue
                transform = None
                if layer.crs().isValid() and layer.crs().authid() != crs.authid():
                    transform = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
                request_rect = extent if transform is None else transform.transformBoundingBox(
                    extent, reverse
                )
                request = QgsFeatureRequest().setFilterRect(request_rect).setNoAttributes()
                layer_pieces: list[Any] = []
                for feature in layer.getFeatures(request):
                    geometry = feature.geometry()
                    if geometry is None or geometry.isEmpty():
                        continue
                    geometry = QgsGeometry(geometry)
                    if transform is not None:
                        geometry.transform(transform)
                    clipped = geometry.intersection(frame_geometry)
                    if clipped is not None and not clipped.isEmpty():
                        layer_pieces.append(clipped)
                if layer_pieces:
                    union = QgsGeometry.unaryUnion(layer_pieces)
                    per_layer.append({"layer": str(layer.name()), "fraction": round(float(union.area()) / frame_area, 3)})
                    pieces.append(union)
                else:
                    per_layer.append({"layer": str(layer.name()), "fraction": 0.0})
            except Exception:
                continue
        if polygon_layers == 0:
            return None
        union_all = QgsGeometry.unaryUnion(pieces) if pieces else None
        total = union_all.area() if union_all is not None else 0.0
        # Cobertura por célula (3x3): é o que distingue "estado diagonal com
        # cantos vazios" (normal) de "metade da folha em branco" (defeito).
        cells: list[list[float]] = []
        from qgis.core import QgsRectangle  # type: ignore

        for row in range(3):
            line: list[float] = []
            for col in range(3):
                cell = QgsRectangle(
                    extent.xMinimum() + extent.width() * col / 3.0,
                    extent.yMaximum() - extent.height() * (row + 1) / 3.0,
                    extent.xMinimum() + extent.width() * (col + 1) / 3.0,
                    extent.yMaximum() - extent.height() * row / 3.0,
                )
                cell_area = cell.width() * cell.height()
                covered = 0.0
                if union_all is not None and cell_area > 0:
                    part = union_all.intersection(QgsGeometry.fromRect(cell))
                    covered = float(part.area()) / cell_area if part is not None and not part.isEmpty() else 0.0
                line.append(round(min(1.0, covered), 3))
            cells.append(line)
        return {"fraction": round(min(1.0, float(total) / frame_area), 3), "layers": per_layer, "cells": cells}
    except Exception:
        return None


def collect_label_results(map_item: Any, dpi: int = 150) -> dict[str, Any] | None:
    """Rótulos colocados e descartados ao renderizar o quadro.

    O motor de rótulos do QGIS descarta em silêncio um rótulo que colide com
    outro ou cruza a moldura; o mapa sai "bem-sucedido" com feições sem
    nome. Desde o QGIS 3.20 a renderização pode coletar os descartados
    (``CollectUnplacedLabels``): o quadro é renderizado de novo, fora da
    tela, em dpi moderado (a colocação é feita em milímetros de papel, então
    o resultado é o mesmo da exportação), e cada rótulo vem com a camada e o
    texto. ``None`` quando a API não existe ou a renderização falha.
    """
    try:
        from qgis.core import Qgis, QgsMapRendererSequentialJob, QgsProject  # type: ignore
        from qgis.PyQt.QtCore import QSizeF  # type: ignore
    except Exception:
        return None
    try:
        size = map_item.sizeWithUnits()
        width_px = max(16, int(float(size.width()) / 25.4 * dpi))
        height_px = max(16, int(float(size.height()) / 25.4 * dpi))
        settings = map_item.mapSettings(map_item.extent(), QSizeF(width_px, height_px), float(dpi), True)
        engine = settings.labelingEngineSettings()
        flag_enum = getattr(Qgis, "LabelingFlag", None)
        if flag_enum is not None:
            engine.setFlag(flag_enum.CollectUnplacedLabels, True)
        else:  # QGIS < 3.30: bandeira na própria classe de configurações
            engine.setFlag(type(engine).CollectUnplacedLabels, True)
        settings.setLabelingEngineSettings(engine)
        job = QgsMapRendererSequentialJob(settings)
        job.start()
        job.waitForFinished()
        results = job.takeLabelingResults()
        if results is None:
            return None
        labels = results.allLabels()
    except Exception:
        return None

    project = None
    try:
        project = QgsProject.instance()
    except Exception:
        pass
    by_layer: dict[str, dict[str, int]] = {}
    unplaced_sample: list[dict[str, str]] = []
    placed = unplaced = 0
    for label in labels:
        try:
            layer = project.mapLayer(label.layerID) if project is not None else None
            name = str(layer.name()) if layer is not None else str(label.layerID)
            bucket = by_layer.setdefault(name, {"placed": 0, "unplaced": 0})
            if bool(getattr(label, "isUnplaced", False)):
                unplaced += 1
                bucket["unplaced"] += 1
                if len(unplaced_sample) < 12:
                    unplaced_sample.append({"layer": name, "text": str(getattr(label, "labelText", ""))})
            else:
                placed += 1
                bucket["placed"] += 1
        except Exception:
            continue
    return {
        "placed": placed,
        "unplaced": unplaced,
        "by_layer": by_layer,
        "unplaced_sample": unplaced_sample,
        "render_dpi": dpi,
    }


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
    # A barra mede o quadro a que está ligada, que nem sempre é o principal
    # (num painel duplo cada quadro tem a sua).
    linked = _safe(scalebar_item.linkedMap, None) or map_item
    scale = float(_safe(linked.scale, 0.0) or 0.0) if linked is not None else 0.0
    factor = {"km": 1000.0, "m": 1.0, "cm": 0.01, "mi": 1609.344, "ft": 0.3048}.get(unit_label.strip().lower())
    if scale > 0 and factor and units_per_segment > 0 and (segments + segments_left) > 0:
        total_ground = units_per_segment * (segments + segments_left) * factor
        bar_width_mm = (total_ground / scale) * 1000.0
        if frame_width > 0:
            fraction = bar_width_mm / frame_width

    font_pt = None
    try:
        text_format = scalebar_item.textFormat()
        font_pt = float(text_format.size())
        unit = str(getattr(text_format.sizeUnit(), "name", text_format.sizeUnit())).lower()
        if "millimeter" in unit or unit in ("0", "rendermillimeters"):
            font_pt = font_pt / (25.4 / 72.0)  # o corpo foi dado em mm
    except Exception:
        try:
            font_pt = float(scalebar_item.font().pointSizeF())
        except Exception:
            font_pt = None

    return {
        "item_id": _safe(scalebar_item.id, "") or "",
        "label_font_pt": font_pt,
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


def _load_image(png_path: str | Path) -> Any:
    try:
        from qgis.PyQt.QtGui import QImage  # type: ignore
    except Exception:
        return None
    try:
        # O Qt 6 recusa por padrão imagens acima de 256 MB decodificados: um A1
        # a 300 dpi não abria, e as medidas no raster diziam "sem raster".
        from qgis.PyQt.QtGui import QImageReader  # type: ignore

        if hasattr(QImageReader, "setAllocationLimit"):
            QImageReader.setAllocationLimit(2048)
    except Exception:
        pass
    image = QImage(str(png_path))
    return None if image.isNull() else image


def _pixel_box(image: Any, rect_mm: dict[str, float], page_mm: tuple[float, float]) -> tuple[int, int, int, int] | None:
    page_width, page_height = page_mm
    if page_width <= 0 or page_height <= 0:
        return None
    scale_x = image.width() / page_width
    scale_y = image.height() / page_height
    left = max(0, int(rect_mm["x"] * scale_x))
    top = max(0, int(rect_mm["y"] * scale_y))
    right = min(image.width(), int((rect_mm["x"] + rect_mm["width"]) * scale_x))
    bottom = min(image.height(), int((rect_mm["y"] + rect_mm["height"]) * scale_y))
    if right - left < 2 or bottom - top < 2:
        return None
    return left, top, right, bottom


def _sample_ink(image: Any, box: tuple[int, int, int, int], steps: int = 140, uniform_is_blank: bool = True) -> float | None:
    """Fração de amostras com tinta numa caixa de pixels.

    Amostragem em grade: percorrer milhões de pixels dentro do QGIS trava a
    interface. ~140x140 amostras bastam para distinguir mapa de folha branca.
    Pixel transparente não é tinta: uma exportação que não desenhou nada —
    todos os pixels em (0,0,0,0) — era contada como 100% de tinta e passava na
    regra de quadro em branco.
    """
    left, top, right, bottom = box
    step_x = max(1, (right - left) // steps)
    step_y = max(1, (bottom - top) // steps)
    total = inked = opaque = 0
    seen: set[int] = set()
    for y in range(top, bottom, step_y):
        for x in range(left, right, step_x):
            total += 1
            pixel = image.pixel(x, y)
            alpha = (pixel >> 24) & 0xFF
            red, green, blue = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF
            seen.add(pixel)
            if alpha < 8:
                continue
            opaque += 1
            if red < 246 or green < 246 or blue < 246:
                inked += 1
    if total == 0:
        return None
    if opaque == 0:
        return 0.0
    # Cor única no QUADRO INTEIRO significa que nada foi renderizado; numa
    # célula ou numa faixa, uma cor única é só uma área uniformemente pintada.
    if uniform_is_blank and len(seen) <= 1:
        return 0.0
    return inked / total


#: Mais camadas que isto no quadro e a medida camada a camada não é feita: cada
#: camada é uma renderização, e a auditoria roda na thread da interface.
MAX_MEASURED_LAYERS = 12


def _item_settings(map_item: Any, width_px: int, labels: bool = True) -> Any:
    """As configurações de renderização do próprio quadro, numa largura em pixels.

    Vêm de ``QgsLayoutItemMap.mapSettings``, como na exportação: mesma escala
    (o dpi é o que faz ``width_px`` corresponder à largura do quadro no
    papel), mesmo contexto de expressões (``@map_scale``), mesma rotação,
    mesmo tema de camadas. Montar um ``QgsMapSettings`` do zero renderizava
    noutra escala: camadas com visibilidade por escala sumiam da medida
    embora aparecessem no PNG, e a auditoria as dava por cobertas.
    """
    from qgis.PyQt.QtCore import QSizeF  # type: ignore
    from qgis.PyQt.QtGui import QColor  # type: ignore

    rect = map_item.rect()
    width_mm, height_mm = float(rect.width()), float(rect.height())
    extent = map_item.extent()
    if width_mm <= 0 or height_mm <= 0 or extent.isEmpty():
        return None
    height_px = max(1, int(round(width_px * height_mm / width_mm)))
    dpi = width_px * 25.4 / width_mm
    settings = map_item.mapSettings(extent, QSizeF(width_px, height_px), dpi, True)
    settings.setBackgroundColor(QColor(255, 255, 255, 0))
    if not labels:
        try:
            from qgis.core import Qgis, QgsMapSettings  # type: ignore

            flag = getattr(getattr(Qgis, "MapSettingsFlag", None), "DrawLabeling", None) or getattr(QgsMapSettings, "DrawLabeling")
            settings.setFlag(flag, False)
        except Exception:
            pass
    return settings


def _render_layers(map_item: Any, layers: list[Any], width_px: int, labels: bool = True) -> Any:
    """As camadas renderizadas sozinhas, como o quadro as desenha, sobre fundo transparente."""
    from qgis.core import QgsMapRendererCustomPainterJob  # type: ignore
    from qgis.PyQt.QtGui import QImage, QPainter  # type: ignore

    from .qtcompat import qt_enum

    settings = _item_settings(map_item, width_px, labels)
    if settings is None:
        return None
    settings.setLayers(list(layers))
    size = settings.outputSize()
    image = QImage(size.width(), size.height(), qt_enum(QImage, "Format", "Format_ARGB32"))
    image.fill(0)
    painter = QPainter(image)
    job = QgsMapRendererCustomPainterJob(settings, painter)
    job.start()
    job.waitForFinished()
    painter.end()
    return image


def _value_scales(map_item: Any) -> list[dict[str, Any]]:
    """A régua de cor ou de tamanho de cada camada temática do quadro (CART081).

    Mapa de calor (com o máximo automático ou fixo), classes graduadas (os
    limites) e símbolo proporcional (o domínio de valores e os tamanhos), com
    a variável de cada um: é o que dois painéis precisam ter igual para que
    o leitor compare cor com cor e tamanho com tamanho.
    """
    out: list[dict[str, Any]] = []
    try:
        for layer in _frame_layers(map_item, None):
            renderer = _safe(layer.renderer)
            kind = str(_safe(renderer.type, "") or "") if renderer is not None else ""
            entry: dict[str, Any] | None = None
            if kind == "heatmapRenderer":
                entry = {"kind": "heatmap", "variable": str(_safe(renderer.weightExpression, "") or ""),
                         "maximum": float(_safe(renderer.maximumValue, 0.0) or 0.0),
                         "radius": float(_safe(renderer.radius, 0.0) or 0.0)}
            elif kind == "graduatedSymbol":
                entry = {"kind": "graduated", "variable": str(_safe(renderer.classAttribute, "") or ""),
                         "breaks": [round(float(r.lowerValue()), 6) for r in renderer.ranges()]
                         + [round(float(r.upperValue()), 6) for r in list(renderer.ranges())[-1:]]}
            elif kind == "singleSymbol":
                symbol = _safe(renderer.symbol)
                size = _safe(symbol.dataDefinedSize) if symbol is not None else None
                transformer = _safe(size.transformer) if size is not None and _safe(size.isActive, False) else None
                if transformer is not None and hasattr(transformer, "minValue"):
                    entry = {"kind": "proportional", "variable": str(_safe(size.field, "") or _safe(size.expressionString, "") or ""),
                             "domain": [float(transformer.minValue()), float(transformer.maxValue())],
                             "sizes": [float(transformer.minSize()), float(transformer.maxSize())]}
            if entry is not None:
                out.append({"layer": str(layer.name()), **entry})
    except Exception:
        return out
    return out


def _frame_layers(map_item: Any, layers: list[Any] | None) -> list[Any]:
    """As camadas do quadro, da que fica por cima para a de baixo (a ordem do QGIS)."""
    drawn = list(layers or [])
    if not drawn:
        # Quadro que segue o projeto (ou um tema): a lista é a que o próprio
        # quadro renderizaria, e não as camadas marcadas na árvore.
        settings = _item_settings(map_item, 64)
        drawn = list(settings.layers()) if settings is not None else []
    return [layer for layer in drawn if layer is not None and layer.isValid()]


def _occludes(layer: Any) -> bool:
    """A camada cobre o que está embaixo? Só no modo de mistura normal.

    Um sombreamento em "multiplicar" sobre um modelo de elevação modula as
    cores de baixo em vez de escondê-las; contá-lo como cobertura acusaria
    o desenho clássico de relevo.
    """
    try:
        from qgis.PyQt.QtGui import QPainter  # type: ignore

        from .qtcompat import qt_enum

        return layer.blendMode() == qt_enum(QPainter, "CompositionMode", "CompositionMode_SourceOver")
    except Exception:
        return True


def _erode(mask: Any) -> Any:
    """Erosão de um pixel (vizinhança em cruz) de uma máscara booleana numpy."""
    out = mask.copy()
    out[1:, :] &= mask[:-1, :]
    out[:-1, :] &= mask[1:, :]
    out[:, 1:] &= mask[:, :-1]
    out[:, :-1] &= mask[:, 1:]
    out[0, :] = out[-1, :] = False
    out[:, 0] = out[:, -1] = False
    return out


def measure_layer_stack(map_item: Any, layers: list[Any] | None = None, width_px: int = 400) -> dict[str, Any] | None:
    """Tinta do quadro e, por camada, quanto do que ela desenha fica à vista.

    Cada camada é renderizada sozinha, sem rótulos, como o quadro a desenha;
    o canal alfa diz onde ela pinta e com que opacidade. A cobertura que as
    camadas de cima fazem sobre cada pixel é a composição desses alfas
    (a + b·(1 − a), "por cima de"), e o que fica à vista de uma camada é
    1 − cobertura nos pixels em que ela pinta. Um preenchimento com 85 %
    de opacidade deixa 15 % à vista — contar "pixels que mudam" dava 100 %,
    e um modelo de elevação quase todo escondido sob os municípios passava
    por visível. Sem os rótulos: o motor os desenha por cima de tudo, mas a
    legenda mostra a amostra do símbolo, não os nomes.

    Devolve ``ink_fraction`` (pixels com tinta de alguma camada, CART062),
    ``visible_fraction`` e ``visible_share`` (fração do que a camada pinta
    e fração do quadro em que ela aparece, por nome), ``visible_by_id`` e
    ``empty`` (camadas sem nenhum pixel na extensão). ``None`` sem numpy,
    sem camadas ou com camadas demais.
    """
    try:
        import numpy  # type: ignore

        frame = _frame_layers(map_item, layers)
        drawn = [layer for layer in frame if not _is_label_only_layer(layer)]
        if not drawn or len(drawn) > MAX_MEASURED_LAYERS:
            return None
        cover = None
        union = None
        visible_fraction: dict[str, float] = {}
        visible_share: dict[str, float] = {}
        visible_by_id: dict[str, float] = {}
        empty: list[str] = []
        for layer in drawn:  # de cima para baixo
            pixels = _pixels(_render_layers(map_item, [layer], width_px, labels=False))
            if pixels is None:
                return None
            alpha = pixels[:, :, 3].astype(numpy.float32) / 255.0  # ARGB32 em little-endian: alfa no 4º byte
            if cover is None:
                cover = numpy.zeros_like(alpha)
                union = numpy.zeros_like(alpha)
            ink = alpha >= (8.0 / 255.0)
            name = str(layer.name())
            painted = int(ink.sum())
            if painted == 0:
                visible_fraction[name] = 0.0
                visible_share[name] = 0.0
                visible_by_id[str(layer.id())] = 0.0
                empty.append(name)
            else:
                shown = (1.0 - cover)[ink]
                visible_fraction[name] = round(float(shown.mean()), 4)
                # Fração do quadro em que a camada aparece como MANCHA: a máscara
                # do que fica à vista é erodida de um pixel, o que apaga a lasca
                # de contorno ao longo de uma divisa (uma linha, não uma área)
                # e mantém o mar que sobra em volta de um continente.
                patch = _erode(ink & (cover < 0.5))
                visible_share[name] = round(float(patch.sum()) / float(alpha.size), 4)
                visible_by_id[str(layer.id())] = visible_fraction[name]
            if _occludes(layer):
                cover = cover + alpha * (1.0 - cover)
            union = union + alpha * (1.0 - union)
        inked = union >= (8.0 / 255.0)
        rows, cols = inked.shape
        # Tinta só dos dados, célula a célula (3x3): sem grade, sem rótulos.
        # É o que diz se uma faixa do quadro é papel em branco num mapa de
        # linhas ou pontos, que não tem área de polígono para medir.
        ink_grid = [[round(float(inked[rows * r // 3:rows * (r + 1) // 3, cols * c // 3:cols * (c + 1) // 3].mean()), 4)
                     for c in range(3)] for r in range(3)]
        return {
            "ink_fraction": round(float(inked.mean()), 6),
            "ink_grid": ink_grid,
            "visible_fraction": visible_fraction,
            "visible_share": visible_share,
            "visible_by_id": visible_by_id,
            "empty": empty,
        }
    except Exception:
        return None


def _pixels(image: Any) -> Any:
    """Os pixels ARGB32 como matriz numpy (altura × largura × 4), ou None sem numpy."""
    try:
        import numpy  # type: ignore

        pointer = image.constBits()
        pointer.setsize(image.sizeInBytes() if hasattr(image, "sizeInBytes") else image.byteCount())
        rows = numpy.frombuffer(pointer, numpy.uint8).reshape(image.height(), image.bytesPerLine())
        # Cópia, e não uma vista: a vista lê a memória da QImage, que é liberada
        # quando a imagem temporária sai de escopo — e a medida passava a ler
        # memória reaproveitada (pixels "pintados" numa camada vazia).
        return rows[:, : image.width() * 4].reshape(image.height(), image.width(), 4).copy()
    except Exception:
        return None


def _opaque_count(image: Any) -> int:
    pixels = _pixels(image)
    if pixels is not None:
        return int((pixels[:, :, 3] >= 8).sum())  # ARGB32 em little-endian: o alfa é o 4º byte
    return sum(1 for y in range(image.height()) for x in range(image.width()) if (image.pixel(x, y) >> 24) & 0xFF >= 8)


def measure_layer_visibility(map_item: Any, layers: list[Any] | None = None, width_px: int = 400) -> dict[str, float] | None:
    """Para cada camada do quadro, que fração do que ela desenha fica à vista (ver ``measure_layer_stack``)."""
    stack = measure_layer_stack(map_item, layers, width_px)
    return None if stack is None else stack["visible_fraction"]


def _visibility_entries(stack: dict[str, Any] | None) -> dict[str, Any]:
    """Camadas escondidas (CART021) e camadas sem nada na extensão, a partir da medida da pilha.

    Escondida é a camada de que menos de ``COVERED_VISIBLE_MAX`` do que ela
    pinta fica à vista e que, além disso, aparece em menos de
    ``COVERED_VISIBLE_SHARE`` do quadro: um oceano que ocupa o quadro inteiro
    com 8 % à vista continua sendo um oceano no mapa.
    """
    from .rulebook import COVERED_VISIBLE_MAX, COVERED_VISIBLE_SHARE

    if stack is None:
        return {"layer_visible_fraction": None, "layer_visible_share": None, "hidden_layer_names": None,
                "empty_layer_names": None, "layer_visible_by_id": None}
    empty = list(stack["empty"])
    hidden = [name for name, fraction in stack["visible_fraction"].items()
              if name not in empty and fraction < COVERED_VISIBLE_MAX
              and stack["visible_share"].get(name, 0.0) < COVERED_VISIBLE_SHARE]
    return {"layer_visible_fraction": stack["visible_fraction"], "layer_visible_share": stack["visible_share"],
            "hidden_layer_names": hidden, "empty_layer_names": empty, "layer_visible_by_id": stack["visible_by_id"]}


def _is_label_only_layer(layer: Any) -> bool:
    try:
        renderer = layer.renderer()
        return renderer is not None and str(renderer.type()) == "nullSymbol"
    except Exception:
        return False


def measure_layer_ink(map_item: Any, layers: list[Any] | None = None, width_px: int = 600) -> float | None:
    """Fração dos pixels em que as camadas do quadro desenham algo (CART062).

    Renderiza só as camadas do quadro, na extensão e no CRS dele, sobre fundo
    transparente — sem moldura, grade, rótulos de coordenada nem nada do
    layout. A tinta medida no PNG exportado não distinguia um quadro vazio de
    um com moldura e linhas de grade: o experimento E1 (paper/tgis) apagou as
    camadas de seis mapas e a regra do quadro em branco passou nos seis.
    Qualquer feição desenhada deixa pixels opacos; zero é quadro vazio.
    """
    try:
        frame = _frame_layers(map_item, layers)
        image = _render_layers(map_item, frame, width_px)
        if image is None:
            return None
        return round(_opaque_count(image) / float(image.width() * image.height()), 6)
    except Exception:
        return None


def chromatic_fraction(pixels: Any, chroma_min: int) -> float | None:
    """Fração dos pixels com tinta que têm cor (pura, testável sem QGIS).

    ``pixels`` são inteiros ARGB como os de ``QImage.pixel``. Tinta é o que
    não é fundo branco nem transparente; cor é croma — o maior canal menos o
    menor — de pelo menos ``chroma_min`` (0–255). Cinzas, inclusive os tons
    do antisserrilhado entre preto e branco, têm croma zero.
    """
    inked = coloured = 0
    for pixel in pixels:
        alpha = (pixel >> 24) & 0xFF
        if alpha < 8:
            continue
        red, green, blue = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF
        if red >= 246 and green >= 246 and blue >= 246:
            continue
        inked += 1
        if max(red, green, blue) - min(red, green, blue) >= chroma_min:
            coloured += 1
    if inked == 0:
        return None
    return coloured / inked


def measure_chromatic_fraction(png_path: str | Path, steps: int = 300) -> float | None:
    """Fração da tinta da página inteira que tem cor (CART073).

    Amostrada numa grade de ``steps`` x ``steps`` pixels, como a tinta do
    quadro: suficiente para achar um contorno vermelho de inserto ou um
    preenchimento azul-claro numa figura pedida em tons de cinza.
    """
    from .rulebook import GREYSCALE_CHROMA_MIN

    image = _load_image(png_path)
    if image is None:
        return None
    width, height = image.width(), image.height()
    step_x = max(1, width // steps)
    step_y = max(1, height // steps)
    pixels = (image.pixel(x, y) for y in range(0, height, step_y) for x in range(0, width, step_x))
    value = chromatic_fraction(pixels, GREYSCALE_CHROMA_MIN)
    return round(value, 5) if value is not None else None


def measure_ink_fraction(png_path: str | Path, map_rect_mm: dict[str, float], page_mm: tuple[float, float]) -> float | None:
    """Fração de pixels não-fundo dentro do quadro do mapa no PNG exportado.

    É a única checagem que enxerga o resultado em vez de confiar na estrutura
    de dados; sem ela, um mapa em branco passa por todos os códigos de retorno.
    """
    image = _load_image(png_path)
    if image is None:
        return None
    box = _pixel_box(image, map_rect_mm, page_mm)
    if box is None or box[2] - box[0] < 8 or box[3] - box[1] < 8:
        return None
    return _sample_ink(image, box)


def measure_ink_grid(
    png_path: str | Path, map_rect_mm: dict[str, float], page_mm: tuple[float, float], cells: int = 3
) -> list[list[float]] | None:
    """Tinta do quadro medida célula a célula numa grade ``cells x cells``.

    Uma fração única não distingue "quadro cheio" de "metade cheia, metade
    vazia"; por célula, a metade vazia aparece.
    """
    image = _load_image(png_path)
    if image is None:
        return None
    grid: list[list[float]] = []
    for row in range(cells):
        line: list[float] = []
        for col in range(cells):
            cell = {
                "x": map_rect_mm["x"] + map_rect_mm["width"] * col / cells,
                "y": map_rect_mm["y"] + map_rect_mm["height"] * row / cells,
                "width": map_rect_mm["width"] / cells,
                "height": map_rect_mm["height"] / cells,
            }
            box = _pixel_box(image, cell, page_mm)
            value = _sample_ink(image, box, steps=60, uniform_is_blank=False) if box is not None else None
            line.append(round(value, 4) if value is not None else 0.0)
        grid.append(line)
    return grid


def measure_surroundings_ink(
    png_path: str | Path,
    item_rect_mm: dict[str, float],
    frame_rect_mm: dict[str, float],
    page_mm: tuple[float, float],
    ring_mm: float = 3.0,
) -> float | None:
    """Tinta na faixa de ``ring_mm`` ao redor de um item sobreposto ao quadro.

    O que está *sob* o item não dá para medir no PNG final (o item está
    desenhado por cima). A faixa em volta é o melhor indício disponível: uma
    rosa dos ventos num canto vazio tem faixa vazia; uma sobre uma cidade
    rotulada, não. A faixa é recortada ao quadro do mapa.
    """
    image = _load_image(png_path)
    if image is None:
        return None
    fx0, fy0 = frame_rect_mm["x"], frame_rect_mm["y"]
    fx1, fy1 = fx0 + frame_rect_mm["width"], fy0 + frame_rect_mm["height"]
    ix0, iy0 = item_rect_mm["x"], item_rect_mm["y"]
    ix1, iy1 = ix0 + item_rect_mm["width"], iy0 + item_rect_mm["height"]
    strips = [
        (ix0 - ring_mm, iy0 - ring_mm, ix1 + ring_mm, iy0),  # acima
        (ix0 - ring_mm, iy1, ix1 + ring_mm, iy1 + ring_mm),  # abaixo
        (ix0 - ring_mm, iy0, ix0, iy1),  # esquerda
        (ix1, iy0, ix1 + ring_mm, iy1),  # direita
    ]
    total = inked = 0.0
    for x0, y0, x1, y1 in strips:
        x0, y0, x1, y1 = max(x0, fx0), max(y0, fy0), min(x1, fx1), min(y1, fy1)
        if x1 - x0 <= 0.2 or y1 - y0 <= 0.2:
            continue
        box = _pixel_box(image, {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}, page_mm)
        if box is None:
            continue
        value = _sample_ink(image, box, steps=40, uniform_is_blank=False)
        if value is None:
            continue
        area = (x1 - x0) * (y1 - y0)
        total += area
        inked += value * area
    if total <= 0:
        return None
    return round(inked / total, 4)
