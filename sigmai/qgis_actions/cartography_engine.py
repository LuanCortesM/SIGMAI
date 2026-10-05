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
    subject_ids = params.get("subject_layer_id")
    if not subject_ids and recipe:
        subject_ids = (recipe.get("params") or {}).get("subject_layer_id")
    if subject_ids and main_item is not None:
        data_extent = _subject_extent(subject_ids, main_item, notes)

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
    )
    report["layout_name"] = layout_name
    if notes:
        report["notes"] = list(report.get("notes") or []) + notes
    return report


def _subject_extent(subject_ids: Any, map_item: Any, notes: list[str]) -> dict[str, float] | None:
    """Extensão, no CRS do quadro, das camadas de assunto (uma id ou lista)."""
    ids = [subject_ids] if isinstance(subject_ids, str) else [str(value) for value in (subject_ids or [])]
    try:
        from qgis.core import QgsCoordinateTransform  # type: ignore

        union = None
        for layer_id in ids:
            layer = project().mapLayer(layer_id)
            if layer is None:
                notes.append(f"subject_layer_id {layer_id!r} não está no projeto; CART061 ignora essa camada.")
                continue
            transform = QgsCoordinateTransform(layer.crs(), map_item.crs(), project())
            extent = transform.transformBoundingBox(layer.extent())
            if union is None:
                union = extent
            else:
                union.combineExtentWith(extent)
        if union is None or union.isEmpty():
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
    # projeto foi reaberto e os ids mudaram, pelo nome.
    proj = project()
    remapped: dict[str, str] = {}
    missing: list[str] = []
    for layer in recipe.get("layers") or []:
        layer_id, name = str(layer.get("id") or ""), str(layer.get("name") or "")
        if proj.mapLayer(layer_id) is not None:
            continue
        by_name = [c for c in proj.mapLayers().values() if c.name() == name]
        if by_name:
            remapped[layer_id] = by_name[0].id()
        else:
            missing.append(name or layer_id)
    if missing:
        raise ValidationError(
            "LAYER_NOT_FOUND",
            "Camadas da receita não estão no projeto: " + ", ".join(repr(m) for m in missing) +
            ". Carregue-as (load_vector_layer) com o mesmo nome antes de recompor.",
            {"missing": missing},
        )

    def _remap(value: Any) -> Any:
        if isinstance(value, str):
            return remapped.get(value, value)
        if isinstance(value, list):
            return [_remap(v) for v in value]
        if isinstance(value, dict):
            return {k: _remap(v) for k, v in value.items()}
        return value

    if remapped:
        compose_params = _remap(compose_params)
    if "layout_name" not in overrides and recipe.get("layout_name"):
        compose_params["layout_name"] = recipe["layout_name"]

    notes = []
    changes = data_changes(recipe)
    if changes:
        notes.append("Os dados mudaram desde a receita: " + "; ".join(changes) + ". O mapa recomposto reflete os dados atuais.")
    if remapped:
        notes.append(f"{len(remapped)} camada(s) foram localizadas pelo nome porque o id mudou.")
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
