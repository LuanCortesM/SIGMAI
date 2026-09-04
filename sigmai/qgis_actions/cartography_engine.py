"""Adaptadores de comando para o motor cartográfico.

Faz a ponte entre o registro de comandos da bridge e o pacote
``sigmai.cartography``. Mantido curto de propósito: toda a decisão
cartográfica vive no pacote, que é testável sem QGIS.
"""

from __future__ import annotations

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
    try:
        from ..cartography.layoutgrid import Rect

        size = layout.pageCollection().page(0).pageSize()
        page = resolve_page({"width_mm": float(size.width()), "height_mm": float(size.height()), "name": "detectada"})
        for item in layout.items():
            if type(item).__name__ == "QgsLayoutItemMap":
                position = item.positionWithUnits()
                extent = item.sizeWithUnits()
                map_frame = Rect(float(position.x()), float(position.y()), float(extent.width()), float(extent.height()))
                break
    except Exception:
        pass

    report = audit_layout(
        layout,
        page=page,
        output_path=str(params.get("output_path") or "") or None,
        map_frame=map_frame,
    )
    report["layout_name"] = layout_name
    return report


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
