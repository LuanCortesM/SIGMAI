"""Adaptadores de comando para o motor cartográfico.

Faz a ponte entre o registro de comandos da bridge e o pacote
``sigmai.cartography``. Mantido curto de propósito: toda a decisão
cartográfica vive no pacote, que é testável sem QGIS.
"""

from __future__ import annotations

import json
from pathlib import Path

from typing import Any

from ..cartography.compose import CompositionError, audit_layout, compose_map as _compose_map
from ..cartography.layoutgrid import TEMPLATES, solve_layout
from ..cartography.pagespec import PAGE_SIZES, resolve_page
from ..cartography.rulebook import rulebook_manifest
from ..validators import ValidationError, require_param
from .common import project


def compose_map(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Compõe, exporta e audita um mapa completo."""
    try:
        return _compose_map(params, context)
    except CompositionError as exc:
        raise ValidationError("COMPOSITION_FAILED", str(exc), {"action": "compose_map"}) from exc


def audit_map_layout(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Roda o regulamento cartográfico contra um layout já existente."""
    layout_name = require_param(params, "layout_name", str)
    layout = project().layoutManager().layoutByName(layout_name)
    if layout is None:
        available = [item.name() for item in project().layoutManager().layouts()]
        raise ValidationError(
            "LAYOUT_NOT_FOUND",
            f"Layout não encontrado: {layout_name}.",
            {"layout_name": layout_name, "available": available},
        )

    page = None
    map_frame = None
    main_item = None
    notes: list[str] = []
    # Um layout composto pelo SIGMAI carrega a receita: as margens e a largura
    # impressa da composição valem para a auditoria. Sem isso, a figura de
    # revista (margens de 5 mm por desenho) era auditada com os 10 mm padrão e
    # reprovava em CART041 pelo que a própria composição tinha decidido.
    try:
        recipe = _recipe_of_layout(layout)
    except ValidationError:
        recipe = None
    recipe_margins = None
    recipe_print_width = None
    if recipe:
        recipe_margins = (recipe.get("page") or {}).get("margins_mm")
        recipe_print_width = recipe.get("print_width_mm")
    try:
        from ..cartography.layoutgrid import Rect

        size = layout.pageCollection().page(0).pageSize()
        width_mm, height_mm = float(size.width()), float(size.height())
        page = resolve_page(
            {"width_mm": width_mm, "height_mm": height_mm, "name": "detectada"},
            orientation="portrait" if height_mm > width_mm else "landscape",
            margin_mm=recipe_margins if isinstance(recipe_margins, dict) else None,
        )
        if isinstance(recipe_margins, dict):
            notes.append("Margens tomadas da receita da composição (layout composto pelo SIGMAI).")
        # O quadro que se mede é o principal: o de id "main_map" ou, num
        # layout feito à mão (sem ids), o maior. Pegar "o primeiro que
        # aparecer" media a tinta do inserto e acusava o mapa de estar em
        # branco.
        candidates = []
        for item in layout.items():
            if type(item).__name__ == "QgsLayoutItemMap":
                position = item.positionWithUnits()
                extent = item.sizeWithUnits()
                rect = Rect(float(position.x()), float(position.y()), float(extent.width()), float(extent.height()))
                candidates.append((str(item.id() or ""), rect, item))
        if candidates:
            named = [(rect, item) for item_id, rect, item in candidates if item_id == "main_map"]
            map_frame, main_item = named[0] if named else max(
                ((rect, item) for _, rect, item in candidates), key=lambda pair: pair[0].width * pair[0].height)
    except Exception:
        pass

    # CART061 (a extensão contém os dados) precisa saber o que é "o dado": o
    # assunto. Num layout composto pelo SIGMAI ele vem da receita; em qualquer
    # outro, de subject_layer_id. Sem nenhum dos dois a regra fica sem
    # avaliação — usar todas as camadas acusaria qualquer mapa ampliado sobre
    # uma camada de contexto maior que ele.
    data_extent = None
    subject_layers: list[Any] = []
    subject_ids = params.get("subject_layer_id")
    if not subject_ids and recipe:
        subject_ids = (recipe.get("params") or {}).get("subject_layer_id")
    if subject_ids:
        subject_layers = _subject_layers(subject_ids, notes)
    if subject_layers and main_item is not None:
        data_extent = _subject_extent(subject_layers, main_item, notes)

    print_width = params.get("print_width_mm")
    try:
        print_width_mm = float(print_width) if print_width not in (None, "") else None
    except (TypeError, ValueError):
        raise ValidationError("BAD_REQUEST", f"print_width_mm precisa ser um número em milímetros; recebido {print_width!r}.", {})
    if print_width_mm is None and recipe_print_width:
        try:
            print_width_mm = float(recipe_print_width)
            notes.append(f"Largura impressa de {print_width_mm:g} mm tomada da receita (figura para periódico).")
        except (TypeError, ValueError):
            pass
    # Figura pedida em tons de cinza: pelo parâmetro (qualquer layout) ou pela
    # receita (layout composto pelo SIGMAI com colour_mode='greyscale').
    from ..cartography.params import ParameterError
    from ..cartography.symbology import normalize_colour_mode

    requested_mode = params.get("colour_mode")
    if requested_mode in (None, "") and recipe:
        requested_mode = (recipe.get("params") or {}).get("colour_mode")
        if requested_mode:
            notes.append(f"colour_mode={requested_mode!r} tomado da receita da composição.")
    try:
        colour_mode = normalize_colour_mode(requested_mode)
    except ParameterError as exc:
        raise ValidationError("BAD_REQUEST", str(exc), {"colour_mode": requested_mode})
    report = audit_layout(
        layout,
        page=page,
        output_path=str(params.get("output_path") or "") or None,
        data_extent=data_extent,
        map_frame=map_frame,
        print_width_mm=print_width_mm,
        colour_mode=colour_mode,
        subject_layer_ids=[layer.id() for layer in subject_layers],
    )
    report["layout_name"] = layout_name
    if notes:
        report["notes"] = list(report.get("notes") or []) + notes
    return report


def _subject_layers(subject_ids: Any, notes: list[str]) -> list[Any]:
    """As camadas de assunto, dadas por id ou por nome, uma ou várias (como o compose_map aceita)."""
    if isinstance(subject_ids, (str, int, float)):
        wanted = [str(subject_ids)]
    elif isinstance(subject_ids, (list, tuple, set)):
        wanted = [str(value) for value in subject_ids if value not in (None, "")]
    else:
        notes.append(f"subject_layer_id {subject_ids!r} não é uma id nem uma lista de ids; assunto ignorado.")
        return []
    layers = []
    for key in wanted:
        layer = project().mapLayer(key)
        if layer is None:
            by_name = project().mapLayersByName(key)
            layer = by_name[0] if by_name else None
        if layer is None:
            notes.append(f"subject_layer_id {key!r} não está no projeto; CART061 e CART075 ignoram essa camada.")
            continue
        layers.append(layer)
    return layers


def _subject_extent(subject_layers: list[Any], map_item: Any, notes: list[str]) -> dict[str, float] | None:
    """Extensão, no CRS do quadro, das camadas de assunto."""
    try:
        from qgis.core import QgsCoordinateTransform  # type: ignore

        union = None
        for layer in subject_layers:
            transform = QgsCoordinateTransform(layer.crs(), map_item.crs(), project())
            extent = transform.transformBoundingBox(layer.extent())
            if union is None:
                union = extent
            else:
                union.combineExtentWith(extent)
        # Um ponto só tem extensão de área zero, mas tem posição: só um
        # retângulo nulo (camada vazia) é "sem extensão".
        if union is None or union.isNull():
            return None
        return {"xmin": union.xMinimum(), "ymin": union.yMinimum(), "xmax": union.xMaximum(), "ymax": union.yMaximum()}
    except Exception as exc:
        notes.append(f"Extensão do assunto não calculada ({type(exc).__name__}); CART061 sem avaliação.")
        return None


def get_cartographic_rulebook(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Devolve o regulamento cartográfico, opcionalmente filtrado por categoria."""
    manifest = rulebook_manifest()
    category = str(params.get("category", "")).strip()
    if category:
        selected = manifest["categories"].get(category)
        if selected is None:
            raise ValidationError(
                "UNKNOWN_CATEGORY",
                f"Categoria desconhecida: {category}.",
                {"available": sorted(manifest["categories"])},
            )
        manifest["categories"] = {category: selected}
        manifest["rule_count"] = len(selected)
    manifest["page_sizes"] = sorted(PAGE_SIZES)
    manifest["templates"] = {name: config["description"] for name, config in TEMPLATES.items()}
    return manifest


def plan_map_layout(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Resolve um template numa página sem tocar no projeto.

    Útil para o agente mostrar ao usuário onde cada elemento vai ficar antes de
    pedir autorização para compor.
    """
    plan = solve_layout(
        page=params.get("page"),
        template=str(params.get("template", "cientifico")),
        include_legend=bool(params.get("include_legend", True)),
        include_scale_bar=bool(params.get("include_scale_bar", True)),
        include_scale_text=bool(params.get("include_scale_text", True)),
        include_north_arrow=bool(params.get("include_north_arrow", True)),
        include_subtitle=bool(params.get("include_subtitle", True)),
        include_logo=bool(params.get("include_logo", False)),
    )
    return plan.to_dict()


# ---------------------------------------------------------------------------
# Receita reproduzível
# ---------------------------------------------------------------------------

def _layout_by_name(layout_name: str):
    layout = project().layoutManager().layoutByName(layout_name)
    if layout is None:
        available = [item.name() for item in project().layoutManager().layouts()]
        raise ValidationError("LAYOUT_NOT_FOUND", f"Layout não encontrado: {layout_name}.", {"layout_name": layout_name, "available": available})
    return layout


def _recipe_of_layout(layout) -> dict[str, Any]:
    from ..cartography.recipe import RECIPE_PROPERTY, recipe_from_json

    text = ""
    try:
        text = str(layout.customProperty(RECIPE_PROPERTY, "") or "")
    except Exception:
        text = ""
    if not text:
        raise ValidationError(
            "RECIPE_NOT_FOUND",
            f"O layout {layout.name()!r} não tem receita do SIGMAI: ele não foi composto por compose_map "
            "(ou foi composto por uma versão anterior à 1.1.0). Componha-o de novo para gerar a receita.",
            {"layout_name": layout.name()},
        )
    try:
        return recipe_from_json(text)
    except ValueError as exc:
        raise ValidationError("RECIPE_INVALID", str(exc), {"layout_name": layout.name()}) from exc


def _load_recipe(params: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Receita vinda de ``layout_name``, de ``recipe_path`` (JSON ou PNG com metadados) ou de ``recipe`` (objeto)."""
    from ..cartography.recipe import RECIPE_PNG_KEY, recipe_from_json

    if isinstance(params.get("recipe"), dict):
        try:
            return recipe_from_json(json.dumps(params["recipe"])), "recipe"
        except ValueError as exc:
            raise ValidationError("RECIPE_INVALID", str(exc), {}) from exc
    recipe_path = str(params.get("recipe_path") or "").strip()
    if recipe_path:
        path = Path(recipe_path)
        if not path.is_file():
            raise ValidationError("RECIPE_NOT_FOUND", f"Arquivo de receita não encontrado: {path}.", {"recipe_path": recipe_path})
        if path.suffix.lower() == ".png":
            try:
                from qgis.PyQt.QtGui import QImage  # type: ignore

                image = QImage(str(path))
                text = image.text(RECIPE_PNG_KEY) if not image.isNull() else ""
            except Exception:
                text = ""
            if not text:
                raise ValidationError("RECIPE_NOT_FOUND", f"O PNG {path} não carrega uma receita do SIGMAI nos metadados.", {"recipe_path": recipe_path})
        else:
            text = path.read_text(encoding="utf-8")
        try:
            return recipe_from_json(text), str(path)
        except ValueError as exc:
            raise ValidationError("RECIPE_INVALID", str(exc), {"recipe_path": recipe_path}) from exc
    layout_name = str(params.get("layout_name") or "").strip()
    if not layout_name:
        raise ValidationError("BAD_REQUEST", "Informe layout_name, recipe_path (JSON ou PNG) ou recipe.", {})
    return _recipe_of_layout(_layout_by_name(layout_name)), f"layout:{layout_name}"


def get_map_recipe(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Devolve a receita de um layout composto pelo SIGMAI; grava em JSON se ``output_path`` for dado."""
    from ..cartography.recipe import data_changes, recipe_to_json
    from ..security import ensure_parent_exists, normalize_output_path, reject_existing_path_without_confirmation

    recipe, origin = _load_recipe(params)
    written = ""
    output_path = str(params.get("output_path") or "").strip()
    if output_path:
        path = normalize_output_path(output_path)
        if path.suffix.lower() != ".json":
            raise ValidationError("BAD_REQUEST", f"output_path da receita precisa terminar em .json: {path}", {"output_path": output_path})
        ensure_parent_exists(path)
        try:
            reject_existing_path_without_confirmation(path, bool(params.get("confirm_overwrite")))
        except FileExistsError as exc:
            raise ValidationError("FILE_EXISTS", str(exc), {"output_path": str(path)}) from exc
        if not context.get("dry_run"):
            path.write_text(recipe_to_json(recipe), encoding="utf-8")
        written = str(path)
    return {"origin": origin, "recipe": recipe, "data_changes": data_changes(recipe), "written_to": written}


def _recipe_source(entry: dict[str, Any], data_dir: str) -> str:
    """A fonte gravada ou, se o arquivo sumiu, o de mesmo nome em ``data_dir`` (de preferência com o mesmo SHA-256).

    Achado noutro lugar, o caminho novo vai para ``entry["file"]``: ``data_changes``
    compara então o arquivo que de fato entrou no mapa com o da receita.
    """
    from ..cartography.recipe import file_fingerprint, local_file_of_source

    source = str(entry.get("source") or "")
    path, bar, rest = source.partition("|")
    if not path or local_file_of_source(source) or not data_dir or "://" in path or not Path(data_dir).is_dir():
        return source
    candidates = [c for c in sorted(Path(data_dir).rglob(Path(path).name)) if c.is_file()]
    if not candidates:
        return source
    wanted = (entry.get("file") or {}).get("sha256")
    chosen = next((c for c in candidates if wanted and file_fingerprint(c).get("sha256") == wanted), candidates[0])
    if entry.get("file"):
        entry["file"] = {**entry["file"], "path": str(chosen)}
    return str(chosen) + bar + rest


def _recipe_layer_reachable(entry: dict[str, Any], data_dir: str) -> bool:
    """Para a simulação: a camada pode ser recarregada (arquivo alcançável) ou refeita (comando gravado)?"""
    from ..cartography.recipe import local_file_of_source

    if (entry.get("derived_by") or {}).get("command") == "add_context_annotations":
        return True
    provider = str(entry.get("provider") or "")
    source = _recipe_source(entry, data_dir)
    if provider in ("memory", "") or not source or "<omitido>" in source:
        return False
    return bool(local_file_of_source(source)) or "://" in source or "url=" in source


#: Parâmetros de add_context_annotations que apontam para outra camada: mudam de um projeto para outro.
_ANNOTATION_LAYER_PARAMS = ("boundary_layer_id", "label_within_layer_id")


def _same_recipe_data(layer: Any, entry: dict[str, Any]) -> bool:
    """A camada achada pelo nome tem os dados da receita? Mesmo arquivo (ou, se ele sumiu, mesmo nome de arquivo) ou mesmo comando."""
    import json
    import os

    from .project_overview import redact_layer_source

    made = entry.get("derived_by") if isinstance(entry.get("derived_by"), dict) else None
    if made:
        try:
            current = json.loads(str(layer.customProperty("sigmai/derived_by", "") or "{}"))
        except ValueError:
            return False
        if not isinstance(current, dict):
            return False

        def _without_ids(record: dict[str, Any]) -> tuple[Any, ...]:
            kept = {k: v for k, v in (record.get("params") or {}).items() if k not in _ANNOTATION_LAYER_PARAMS}
            return record.get("command"), record.get("kind"), json.dumps(kept, sort_keys=True)

        return _without_ids(current) == _without_ids(made)
    recorded = str(entry.get("source") or "")
    if not recorded:
        return True
    source = redact_layer_source(layer)
    if source == recorded:
        return True
    recorded_path, _, recorded_rest = recorded.partition("|")
    path, _, rest = source.partition("|")
    if rest != recorded_rest or Path(path).name.lower() != Path(recorded_path).name.lower():
        return False
    if not Path(recorded_path).exists():
        return True  # o arquivo da receita não está nesta máquina: vale o de mesmo nome
    # realpath também expande nomes curtos do Windows (03SIGM~1).
    return os.path.normcase(os.path.realpath(path)) == os.path.normcase(os.path.realpath(recorded_path))


def _follow_moved_file(layer: Any, entry: dict[str, Any]) -> None:
    """Se o arquivo da receita não está nesta máquina, data_changes compara com o da camada achada, e não acusa um sumiço."""
    from ..cartography.recipe import local_file_of_source

    recorded = entry.get("file") or {}
    if not recorded.get("path") or Path(str(recorded["path"])).exists():
        return
    here = local_file_of_source(str(layer.source() or ""))
    if here:
        entry["file"] = {**recorded, "path": here}


def _apply_recipe_style(layer: Any, entry: dict[str, Any]) -> None:
    style = str(entry.get("style_qml") or "")
    if style:
        try:
            from qgis.core import QgsMapLayerStyle  # type: ignore

            QgsMapLayerStyle(style).writeToLayer(layer)
        except Exception:
            pass
    if entry.get("smooth_resampling"):
        from .raster_style import _smooth_resampling

        _smooth_resampling(layer)


def _reload_recipe_layer(entry: dict[str, Any], data_dir: str) -> Any:
    """Recarrega uma camada da receita pela fonte gravada; None se ela não é um arquivo alcançável."""
    provider = str(entry.get("provider") or "")
    source = _recipe_source(entry, data_dir)
    if not source or provider in ("memory", "") or "<omitido>" in source:
        return None
    from qgis.core import QgsRasterLayer, QgsVectorLayer  # type: ignore

    name = str(entry.get("name") or "")
    raster = provider in ("gdal", "wms", "wcs", "arcgismapserver", "xyz")
    layer = QgsRasterLayer(source, name, provider) if raster else QgsVectorLayer(source, name, provider)
    if not layer.isValid():
        return None
    _apply_recipe_style(layer, entry)
    project().addMapLayer(layer)
    return layer


def _rederive_recipe_layers(entries: list[dict[str, Any]], remapped: dict[str, str], reloaded: list[str]) -> list[dict[str, Any]]:
    """Refaz as camadas que add_context_annotations criou, uma chamada por conjunto de parâmetros; devolve as que sobram."""
    import json

    from .context_annotations import add_context_annotations

    groups: dict[str, list[dict[str, Any]]] = {}
    left: list[dict[str, Any]] = []
    for entry in entries:
        made = entry.get("derived_by") if isinstance(entry.get("derived_by"), dict) else {}
        if made.get("command") == "add_context_annotations":
            groups.setdefault(json.dumps(made.get("params") or {}, sort_keys=True), []).append(entry)
        else:
            left.append(entry)
    for key, group in groups.items():
        call = {k: (remapped.get(v, v) if isinstance(v, str) else v) for k, v in json.loads(key).items()}
        try:
            made = add_context_annotations(call, {"dry_run": False})
        except Exception:
            left.extend(group)
            continue
        by_kind = {c.get("kind"): c.get("id") for c in made.get("created_layers") or []}
        for entry in group:
            new_id = by_kind.get((entry.get("derived_by") or {}).get("kind"))
            layer = project().mapLayer(new_id) if new_id else None
            if layer is None:
                left.append(entry)
                continue
            _apply_recipe_style(layer, entry)
            if entry.get("name"):
                layer.setName(str(entry["name"]))
            remapped[str(entry.get("id"))] = layer.id()
            reloaded.append(layer.name())
    return left


#: Propriedades de camada que guardam o id de outra camada.
_LAYER_LINK_PROPERTIES = ("sigmai/derived_from", "sigmai/sites_of")


def _relink_recipe_layers(remapped: dict[str, str]) -> None:
    """O estilo gravado traz as propriedades com os ids antigos: aponta-as para as camadas recarregadas."""
    import json

    for new_id in set(remapped.values()):
        layer = project().mapLayer(new_id)
        if layer is None:
            continue
        for key in _LAYER_LINK_PROPERTIES:
            old = str(layer.customProperty(key, "") or "")
            if old in remapped:
                layer.setCustomProperty(key, remapped[old])
        made = str(layer.customProperty("sigmai/derived_by", "") or "")
        if made:
            try:
                record = json.loads(made)
                record["params"] = {k: (remapped.get(v, v) if isinstance(v, str) else v)
                                    for k, v in (record.get("params") or {}).items()}
                layer.setCustomProperty("sigmai/derived_by", json.dumps(record, ensure_ascii=False))
            except (ValueError, AttributeError):
                pass


def _recipe_projected_crs(recipe: dict[str, Any]) -> str:
    """O código do CRS projetado do mapa original ("EPSG:31983"), ou "" se ele era geográfico ou sem código."""
    import re

    code = str(recipe.get("map_crs") or "").strip()
    if not re.fullmatch(r"[A-Za-z]+:\d+", code):
        return ""
    try:
        from qgis.core import QgsCoordinateReferenceSystem  # type: ignore

        crs = QgsCoordinateReferenceSystem(code)
        return code if crs.isValid() and not crs.isGeographic() else ""
    except Exception:
        return ""


def recompose_from_recipe(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Refaz um mapa a partir da receita, com os mesmos parâmetros e ``overrides`` opcionais."""
    from ..cartography.recipe import data_changes

    recipe, origin = _load_recipe(params)
    overrides = params.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise ValidationError("BAD_REQUEST", "overrides precisa ser um objeto com parâmetros de compose_map.", {})
    compose_params = dict(recipe.get("params") or {})
    compose_params.update(overrides)

    # As camadas da receita precisam existir no projeto — pelo id ou, se o
    # projeto foi reaberto e os ids mudaram, pelo nome. As que faltam são
    # recarregadas da fonte gravada (ou procuradas pelo nome do arquivo em
    # data_dir, noutra máquina), com o estilo da receita; as que um comando do
    # SIGMAI criou (divisas, nomes) são refeitas pelo mesmo comando.
    proj = project()
    remapped: dict[str, str] = {}
    pending: list[dict[str, Any]] = []
    by_name_matches: list[tuple[Any, dict[str, Any]]] = []
    for layer in recipe.get("layers") or []:
        layer_id, name = str(layer.get("id") or ""), str(layer.get("name") or "")
        if proj.mapLayer(layer_id) is not None:
            continue
        # O nome só não basta: os locais de count_points_by_site levam o nome
        # dos registros, e o mapa de calor dos registros saía dos locais.
        by_name = [c for c in proj.mapLayers().values() if c.name() == name and _same_recipe_data(c, layer)]
        if by_name:
            remapped[layer_id] = by_name[0].id()
            by_name_matches.append((by_name[0], layer))
            _follow_moved_file(by_name[0], layer)
        else:
            pending.append(layer)
    found_by_name = len(remapped)

    def _remap(value: Any) -> Any:
        if isinstance(value, str):
            return remapped.get(value, value)
        if isinstance(value, list):
            return [_remap(v) for v in value]
        if isinstance(value, dict):
            # data_source é indexado pelo id da camada: a chave muda também.
            return {remapped.get(k, k): _remap(v) for k, v in value.items()}
        return value

    data_dir = str(params.get("data_dir") or "").strip()
    reloaded: list[str] = []
    restyled: list[str] = []
    if not context.get("dry_run"):
        # Achada pelo nome, a camada pode vir de outro mapa, com outro estilo
        # ("Elevation" sombreada num, hipsométrica noutro): vale o da receita.
        from ..cartography.compose import _layer_style_xml

        for match, entry in by_name_matches:
            if entry.get("style_qml") and _layer_style_xml(match) != entry["style_qml"]:
                _apply_recipe_style(match, entry)
                restyled.append(match.name())
    if pending and context.get("dry_run"):
        reloaded = [str(e.get("name") or e.get("id")) for e in pending if _recipe_layer_reachable(e, data_dir)]
        pending = [e for e in pending if not _recipe_layer_reachable(e, data_dir)]
    elif pending:
        still: list[dict[str, Any]] = []
        for entry in pending:
            layer = _reload_recipe_layer(entry, data_dir)
            if layer is None:
                still.append(entry)
            else:
                remapped[str(entry.get("id"))] = layer.id()
                reloaded.append(layer.name())
        pending = _rederive_recipe_layers(still, remapped, reloaded)
    if remapped and not context.get("dry_run"):
        _relink_recipe_layers(remapped)
    if pending:
        missing = [str(e.get("name") or e.get("id")) for e in pending]
        raise ValidationError(
            "LAYER_NOT_FOUND",
            "Camadas da receita não estão no projeto nem puderam ser recarregadas: " + ", ".join(repr(m) for m in missing) +
            ". Passe data_dir com a pasta dos dados, ou carregue-as (load_vector_layer) com o mesmo nome antes de recompor.",
            {"missing": missing},
        )

    if remapped:
        compose_params = _remap(compose_params)
    if "layout_name" not in overrides and recipe.get("layout_name"):
        compose_params["layout_name"] = recipe["layout_name"]

    notes = []
    # A permissão de sobrescrever e o caminho da receita valiam para o mapa
    # original: herdados, a recomposição regravava a receita de origem por cima
    # (e o mapa, se ninguém mudasse output_path). Só valem se vierem em overrides.
    for key in ("recipe_path", "confirm_overwrite"):
        if key not in overrides:
            compose_params.pop(key, None)
    # O sistema de referência do mapa original vai junto: escolhido de novo, ele
    # dependia do projeto em que se recompõe (WGS 84 em vez de SIRGAS 2000).
    pinned = _recipe_projected_crs(recipe) if "map_crs" not in overrides and not compose_params.get("map_crs") else ""
    if pinned:
        compose_params["map_crs"] = pinned
        notes.append(f"Sistema de referência da receita mantido: {pinned}.")
    changes = data_changes(recipe)
    if changes:
        notes.append("Os dados mudaram desde a receita: " + "; ".join(changes) + ". O mapa recomposto reflete os dados atuais.")
    if reloaded:
        verb = "seriam recarregadas" if context.get("dry_run") else "recarregadas"
        notes.append(f"{len(reloaded)} camada(s) {verb} da receita, com o estilo gravado: " + ", ".join(reloaded) + ".")
    if found_by_name:
        notes.append(f"{found_by_name} camada(s) foram localizadas pelo nome porque o id mudou.")
    if restyled:
        notes.append("Estilo da receita reaplicado em: " + ", ".join(restyled) + ".")
    if context.get("dry_run"):
        return {"dry_run": True, "origin": origin, "params": compose_params, "notes": notes, "data_changes": changes}
    result = compose_map(compose_params, context)
    result["recomposed_from"] = origin
    result["data_changes"] = changes
    result["notes"] = list(result.get("notes", [])) + notes
    return result


def describe_map_for_methods(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Parágrafo de Métodos e referência do software para um layout composto pelo SIGMAI."""
    from ..cartography.recipe import methods_paragraph

    recipe, origin = _load_recipe(params)
    language = str(params.get("language") or (recipe.get("params") or {}).get("map_language") or "pt-BR").strip()
    # O nome do CRS sai na língua do parágrafo ("UTM zona 24S", não "zone").
    try:
        from qgis.core import QgsCoordinateReferenceSystem  # type: ignore

        from ..cartography.compose import _localised_crs_label

        crs = QgsCoordinateReferenceSystem(str(recipe.get("map_crs") or ""))
        if crs.isValid():
            recipe = dict(recipe)
            recipe["map_crs_description"] = _localised_crs_label(crs, language).split(" (")[0]
    except Exception:
        pass
    described = methods_paragraph(recipe, language)
    return {"origin": origin, **described, "recipe_created_at": recipe.get("created_at"),
            "sigmai_version": recipe.get("sigmai_version"), "qgis_version": recipe.get("qgis_version")}
