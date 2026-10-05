"""Briefing do projeto em uma chamada.

Nas duas emulações com um assistente remoto, as cinco primeiras chamadas
foram sempre as mesmas: status, panorama do projeto, detalhes de camada,
regulamento cartográfico, capacidades. ``project_briefing`` devolve o
essencial disso de uma vez — o que há no projeto, o que cada camada
contém (com o campo de nome provável, o problema de codificação, se tem
rótulos), o que o usuário liberou, o regulamento resumido e o caminho
recomendado para os pedidos mais comuns — para que o assistente comece a
trabalhar na segunda chamada, não na sexta.
"""

from __future__ import annotations

from typing import Any

from ..cartography.layoutgrid import TEMPLATES
from ..cartography.rulebook import RULES
from ..permissions import COMMAND_PERMISSIONS
from .common import crs_authid, layer_type_name, project
from .encoding import detect_encoding_problem

#: Feições lidas por camada para achar o campo de nome e exemplos.
SAMPLE_LIMIT = 50
NAME_HINTS = ("nome", "name", "nm_", "_nm", "titulo", "título", "label", "descr", "sitio", "site")


def _name_field_and_examples(layer: Any) -> tuple[str | None, list[str]]:
    try:
        fields = [f.name() for f in layer.fields()]
    except Exception:
        return None, []
    text_fields = []
    try:
        text_fields = [f.name() for f in layer.fields() if f.typeName().lower() in ("string", "text", "varchar", "qstring")]
    except Exception:
        pass
    ranked = sorted(text_fields, key=lambda n: (0 if any(h in n.lower() for h in NAME_HINTS) else 1, fields.index(n)))
    for name in ranked:
        values: list[str] = []
        try:
            for index, feature in enumerate(layer.getFeatures()):
                if index >= SAMPLE_LIMIT:
                    break
                value = feature[name]
                if value not in (None, "") and str(value) != "NULL":
                    values.append(str(value))
        except Exception:
            continue
        if values and (len(values) == 1 or len(set(values)) > 1):
            return name, list(dict.fromkeys(values))[:5]
    return None, []


def _layer_entry(layer: Any, tree_visible: bool | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": layer.id(), "name": layer.name(), "type": layer_type_name(layer), "crs": crs_authid(layer.crs()),
        "valid": bool(layer.isValid()), "visible": tree_visible,
    }
    if layer_type_name(layer) == "vector":
        try:
            entry["geometry"] = {0: "Point", 1: "Line", 2: "Polygon"}.get(int(layer.geometryType()), "Unknown")
            entry["feature_count"] = int(layer.featureCount())
        except Exception:
            pass
        name_field, examples = _name_field_and_examples(layer)
        entry["name_field"] = name_field
        entry["name_examples"] = examples
        try:
            entry["labels_enabled"] = bool(layer.labelsEnabled())
        except Exception:
            pass
        try:
            renderer = layer.renderer()
            entry["renderer"] = str(renderer.type()) if renderer is not None else None
        except Exception:
            pass
        problem = detect_encoding_problem(layer)
        if problem is not None:
            entry["encoding_problem"] = problem["hint"]
    try:
        extent = layer.extent()
        if extent is not None and not extent.isEmpty():
            entry["extent"] = {"xmin": round(extent.xMinimum(), 6), "ymin": round(extent.yMinimum(), 6),
                               "xmax": round(extent.xMaximum(), 6), "ymax": round(extent.yMaximum(), 6)}
    except Exception:
        pass
    return entry


def project_briefing(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    qgs = project()
    root = qgs.layerTreeRoot()
    layers = []
    for layer in qgs.mapLayers().values():
        try:
            node = root.findLayer(layer.id())
            visible = bool(node.isVisible()) if node is not None else None
        except Exception:
            visible = None
        layers.append(_layer_entry(layer, visible))

    layouts = []
    try:
        from ..cartography.recipe import RECIPE_PROPERTY

        for layout in qgs.layoutManager().layouts():
            layouts.append({
                "name": layout.name(),
                "composed_by_sigmai": bool(layout.customProperty(RECIPE_PROPERTY, "")),
            })
    except Exception:
        pass

    consent = context.get("consent")
    access: dict[str, Any] = {"available": False}
    if consent is not None:
        try:
            status = consent.status()
            access = {
                "available": True,
                "mode": status.get("mode"), "mode_label": status.get("mode_label"),
                "output_roots": status.get("output_roots", []),
                "limits": status.get("limits", {}), "counters": status.get("counters", {}),
                "never_auto_approved": status.get("never_auto_approved", []),
            }
        except Exception:
            access = {"available": False}

    qgis_version = ""
    try:
        from qgis.core import Qgis  # type: ignore

        qgis_version = str(Qgis.version())
    except Exception:
        pass
    try:
        from ..bridge_server import plugin_version

        sigmai_version = plugin_version()
    except Exception:
        sigmai_version = ""

    rules = [{"id": r.id, "severity": r.severity, "category": r.category, "title": r.title_pt} for r in RULES]
    enabled_actions = sorted(a for a, m in COMMAND_PERMISSIONS.items() if m.enabled)

    encoding_issues = [layer["name"] for layer in layers if layer.get("encoding_problem")]
    invalid = [layer["name"] for layer in layers if not layer.get("valid", True)]
    warnings = []
    if encoding_issues:
        warnings.append("Camadas com codificação errada (nomes com �): " + ", ".join(encoding_issues) + " — use set_layer_encoding.")
    if invalid:
        warnings.append("Camadas inválidas (não renderizam): " + ", ".join(invalid) + ".")
    if not qgs.fileName():
        warnings.append("O projeto ainda não foi salvo em arquivo; a receita dos mapas não terá caminho de projeto.")

    return {
        "sigmai_version": sigmai_version,
        "qgis_version": qgis_version,
        "project": {
            "path": str(qgs.fileName() or ""), "title": str(qgs.title() or ""), "crs": crs_authid(qgs.crs()),
            "crs_is_geographic": bool(qgs.crs().isGeographic()) if qgs.crs().isValid() else None,
            "layer_count": len(layers), "layout_count": len(layouts),
        },
        "layers": layers,
        "layouts": layouts,
        "access": access,
        "rulebook": {"rule_count": len(rules), "rules": rules},
        "templates": {name: cfg["description"] for name, cfg in TEMPLATES.items()},
        "enabled_action_count": len(enabled_actions),
        "warnings": warnings,
        "recommended_paths": {
            "mapa_de_uma_area_com_contexto": "compose_map com layer_ids (assunto + contexto), subject_layer_id no assunto, data_source por camada, include_inset + inset_layer_ids; leia audit.next_actions.",
            "onde_fica_o_que": "spatial_relationship(layer_id, other_layer_id) antes de assumir em que estado/município algo está.",
            "mapa_de_campanha": "Sítios em planilha? load_vector_layer(path='….csv') detecta lon/lat, separador e decimal (x_field/y_field/crs para E/N). Depois compose_campaign_map(points_layer_id, track_layer_id, area_layer_ids, context_layer_ids, inset_layer_ids, coordinate_table_path).",
            "figura_para_revista": "compose_map com journal_column ('single'/'double') ou figure_width_mm, format 'tif', dpi 300-600.",
            "varios_paineis": "compose_map com panels=[{layer_ids...}, ...] (letras (a), (b), (c)…).",
            "reproduzir_ou_citar": "get_map_recipe / recompose_from_recipe / describe_map_for_methods sobre o layout composto.",
            "errou": "undo_last_action desfaz a última escrita no projeto (arquivos em disco ficam).",
        },
    }
