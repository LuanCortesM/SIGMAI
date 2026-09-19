"""Mapa de campanha de campo e tabela de coordenadas dos pontos.

A figura 1 de quase toda dissertação em biologia de campo é a mesma: os
pontos de coleta rotulados, a trilha percorrida, a área de estudo (UC,
fazenda, bacia) em destaque, o entorno como contexto e um inserto dizendo
onde fica. Com ``compose_map`` isso exige várias decisões — ordem das
camadas, qual delas define o recorte, rótulo, inserto, template — que aqui
são tomadas uma vez, com os padrões certos para esse tipo de mapa, e
devolvidas como parâmetros de ``compose_map`` (a receita continua sendo a
do compositor).

``export_coordinate_table`` grava o anexo que acompanha a figura: uma
tabela CSV com os atributos dos pontos e as coordenadas no sistema pedido
(e em latitude/longitude, sempre), para a seção de material examinado ou
o apêndice de sítios amostrais.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..security import ensure_parent_exists, normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param
from .common import crs_authid, layer_type_name, project

#: Campos que costumam carregar o nome do ponto de coleta, do mais ao menos
#: provável. "id"/"cod" ficam por último: "track_fid" também contém "id" e
#: costuma ser zero em todas as linhas.
NAME_FIELD_HINTS = (
    ("nome", "name", "sitio", "sítio", "site", "ponto", "estacao", "estação", "parcela", "plot", "label"),
    ("id", "cod"),
)

#: Acima disto os pontos só são rotulados quando label_field é pedido.
MAX_AUTO_LABELLED_POINTS = 60

#: Chaves de compose_map que compose_campaign_map repassa sem mexer.
PASSTHROUGH = (
    "page", "orientation", "margin_mm", "map_crs", "auto_projected_crs", "margin_percent", "round_scale", "scale",
    "include_legend", "include_scale_bar", "include_scale_text", "include_north_arrow", "include_grid", "grid_style",
    "legend_title", "map_author_email", "organization", "production_date", "notes_text", "map_language",
    "label_font_size", "apply_style", "output_path", "format", "dpi", "confirm_overwrite", "layout_name", "recipe_path",
    "figure_width_mm", "figure_height_mm", "figure_max_height_mm", "journal_column", "inset_zoom_factor",
)


def _layer(layer_id: str, label: str, geometry: int | None = None):
    layer = project().mapLayer(layer_id)
    if layer is None:
        by_name = [c for c in project().mapLayers().values() if c.name() == layer_id]
        layer = by_name[0] if by_name else None
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", f"{label}: camada não encontrada: {layer_id}.", {label: layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", f"{label} precisa ser uma camada vetorial.", {label: layer_id})
    if geometry is not None and int(layer.geometryType()) != geometry:
        kind = {0: "pontos", 1: "linhas", 2: "polígonos"}[geometry]
        raise ValidationError(
            "GEOMETRY_TYPE_MISMATCH", f"{label} precisa ser uma camada de {kind}; {layer.name()!r} não é.",
            {label: layer_id, "geometry_type": int(layer.geometryType())},
        )
    return layer


def _name_field(layer: Any, requested: str) -> str | None:
    names = [f.name() for f in layer.fields()]
    if requested:
        if requested not in names:
            raise ValidationError(
                "FIELD_NOT_FOUND", f"O campo {requested!r} não existe em {layer.name()!r}. Campos: {', '.join(names)}.",
                {"layer_id": layer.id(), "field": requested},
            )
        return requested
    def rank(name: str) -> tuple[int, int]:
        lowered = name.lower()
        for level, hints in enumerate(NAME_FIELD_HINTS):
            if any(h in lowered for h in hints):
                return (level, names.index(name))
        return (len(NAME_FIELD_HINTS), names.index(name))

    # Um campo de nome tem conteúdo E varia entre as feições: "track_fid"
    # igual a 0 em 211 pontos rotularia todos com "0".
    for name in sorted(names, key=rank):
        try:
            values = []
            for index, feature in enumerate(layer.getFeatures()):
                if index >= 200:
                    break
                value = feature[name]
                values.append(None if value is None or str(value) == "NULL" or value == "" else str(value))
            filled = [v for v in values if v is not None]
            if not filled:
                continue
            if len(values) > 1 and len(set(filled)) == 1:
                continue
            return name
        except Exception:
            continue
    return None


def _id_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise ValidationError("BAD_REQUEST", f"{label} precisa ser um id de camada ou uma lista de ids.", {label: value})


def build_campaign_params(params: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    """Parâmetros de compose_map para um mapa de campanha (função pura, testável sem QGIS).

    ``resolved`` traz o que a ação já verificou no projeto: ids e nomes das
    camadas, o campo de rótulo, qual camada tem a maior extensão entre
    pontos e trilha. A ordem de ``layer_ids`` é a ordem de desenho de cima
    para baixo: pontos, trilha, áreas, contexto.
    """
    points = resolved["points"]
    track = resolved.get("track")
    areas = resolved.get("areas") or []
    context_layers = resolved.get("context") or []
    inset = resolved.get("inset") or []

    layer_ids = [points["id"]] + ([track["id"]] if track else []) + [a["id"] for a in areas] + [c["id"] for c in context_layers]
    compose: dict[str, Any] = {
        "layer_ids": layer_ids,
        "template": "campanha",
        "title": str(params.get("title") or f"Pontos de coleta — {points['name']}").strip(),
        "subject_layer_id": list(resolved.get("subject_ids") or [points["id"]]),
        "map_author": str(params.get("map_author") or "").strip(),
        "data_source": params.get("data_source") or "",
        "include_inset": bool(inset),
        "margin_percent": params.get("margin_percent", 15.0),
    }
    if inset:
        compose["inset_layer_ids"] = [i["id"] for i in inset]
    if resolved.get("label_field"):
        compose["label_field"] = resolved["label_field"]
        compose["label_layer_id"] = points["id"]
    subtitle = str(params.get("subtitle") or "").strip()
    dates = str(params.get("campaign_dates") or "").strip()
    if not subtitle and dates:
        subtitle = f"Campanha de campo: {dates}"
    if subtitle:
        compose["subtitle"] = subtitle
    for key in PASSTHROUGH:
        if key in params and params[key] is not None and key not in compose:
            compose[key] = params[key]
    return compose


def compose_campaign_map(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Pontos + trilha + área + contexto + inserto, com os padrões de um mapa de campanha."""
    from .cartography_engine import compose_map

    points = _layer(require_param(params, "points_layer_id", str), "points_layer_id", geometry=0)
    track = _layer(params["track_layer_id"], "track_layer_id", geometry=1) if params.get("track_layer_id") else None
    areas = [_layer(i, "area_layer_ids", geometry=2) for i in _id_list(params.get("area_layer_ids"), "area_layer_ids")]
    context_layers = [_layer(i, "context_layer_ids") for i in _id_list(params.get("context_layer_ids"), "context_layer_ids")]
    inset = [_layer(i, "inset_layer_ids") for i in _id_list(params.get("inset_layer_ids"), "inset_layer_ids")]
    requested_label = str(params.get("label_field") or "").strip()
    label_field = _name_field(points, requested_label)
    dense_points = False
    if label_field and not requested_label and int(points.featureCount()) > MAX_AUTO_LABELLED_POINTS:
        # 200 pontos de trilha rotulados um a um viram uma nuvem de números
        # descartados pelo motor (CART068). Rotular só quando pedido.
        dense_points = True
        label_field = None

    # O recorte contém os pontos E a trilha (o assunto de um mapa de campanha
    # é o que foi percorrido e coletado); áreas e contexto só entram se o
    # chamador pedir com subject_layer_id.
    if params.get("subject_layer_id"):
        subject_ids = [_layer(i, "subject_layer_id").id() for i in _id_list(params["subject_layer_id"], "subject_layer_id")]
    else:
        subject_ids = [points.id()] + ([track.id()] if track else [])

    resolved = {
        "points": {"id": points.id(), "name": points.name()},
        "track": {"id": track.id(), "name": track.name()} if track else None,
        "areas": [{"id": a.id(), "name": a.name()} for a in areas],
        "context": [{"id": c.id(), "name": c.name()} for c in context_layers],
        "inset": [{"id": i.id(), "name": i.name()} for i in inset],
        "label_field": label_field,
        "subject_ids": subject_ids,
    }
    compose_params = build_campaign_params(params, resolved)
    notes = []
    if dense_points:
        notes.append(
            f"{points.name()!r} tem {points.featureCount()} pontos: rotular todos produziria rótulos descartados por "
            "colisão, então saíram sem rótulo. Passe label_field para rotular mesmo assim, ou use a camada de "
            "waypoints (sítios) em vez dos pontos de trilha."
        )
    elif label_field is None:
        notes.append(f"Nenhum campo de nome encontrado em {points.name()!r}; os pontos saem sem rótulo. Passe label_field.")
    if track is not None and not params.get("subject_layer_id"):
        notes.append(f"O recorte contém os pontos e a trilha {track.name()!r}.")

    result = compose_map(compose_params, context)
    result["campaign"] = {"resolved": resolved, "compose_params": compose_params}
    result["notes"] = list(result.get("notes", [])) + notes

    table_path = str(params.get("coordinate_table_path") or "").strip()
    if table_path and not context.get("dry_run"):
        table = export_coordinate_table({
            "layer_id": points.id(), "output_path": table_path, "crs": params.get("table_crs"),
            "confirm_overwrite": params.get("confirm_overwrite", False), "delimiter": params.get("table_delimiter"),
        }, context)
        result["coordinate_table"] = table
    elif table_path:
        result["coordinate_table"] = {"dry_run": True, "output_path": table_path}
    return result


def export_coordinate_table(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """CSV com atributos e coordenadas (no CRS pedido e em lat/lon) de cada feição."""
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform  # type: ignore

    layer = _layer(require_param(params, "layer_id", str), "layer_id")
    output = normalize_output_path(require_param(params, "output_path", str))
    if output.suffix.lower() not in (".csv", ".txt"):
        raise ValidationError("BAD_REQUEST", f"output_path precisa terminar em .csv: {output}", {"output_path": str(output)})
    ensure_parent_exists(output)
    try:
        reject_existing_path_without_confirmation(output, bool(params.get("confirm_overwrite")))
    except FileExistsError as exc:
        raise ValidationError("FILE_EXISTS", str(exc), {"output_path": str(output)}) from exc

    delimiter = str(params.get("delimiter") or ",")
    if delimiter not in (",", ";", "\t"):
        raise ValidationError("BAD_REQUEST", "delimiter precisa ser ',', ';' ou tabulação.", {"delimiter": delimiter})
    decimals = int(params.get("decimals") or 6)
    fields_wanted = params.get("fields")
    all_fields = [f.name() for f in layer.fields()]
    if fields_wanted is None:
        fields = all_fields
    else:
        if not isinstance(fields_wanted, list):
            raise ValidationError("BAD_REQUEST", "fields precisa ser uma lista de nomes de campo.", {})
        missing = [f for f in fields_wanted if f not in all_fields]
        if missing:
            raise ValidationError("FIELD_NOT_FOUND", f"Campos inexistentes: {', '.join(missing)}. Campos: {', '.join(all_fields)}.", {"missing": missing})
        fields = list(fields_wanted)

    source_crs = layer.crs()
    if not source_crs.isValid():
        raise ValidationError("INVALID_CRS", f"A camada {layer.name()!r} não tem CRS válido.", {"layer_id": layer.id()})
    target_text = str(params.get("crs") or "").strip() or crs_authid(source_crs)
    target = QgsCoordinateReferenceSystem(target_text)
    if not target.isValid():
        raise ValidationError("BAD_REQUEST", f"crs inválido: {target_text!r}. Use um código como 'EPSG:31984'.", {"crs": target_text})
    geographic = QgsCoordinateReferenceSystem("EPSG:4326")
    to_target = QgsCoordinateTransform(source_crs, target, project()) if crs_authid(target) != crs_authid(source_crs) else None
    to_geo = QgsCoordinateTransform(source_crs, geographic, project())

    geometry_type = int(layer.geometryType())
    notes: list[str] = []
    if geometry_type != 0:
        notes.append("A camada não é de pontos: as coordenadas são do ponto representativo (interior) de cada feição.")
    x_name, y_name = ("E", "N") if not target.isGeographic() else ("lon", "lat")
    header = ["fid"] + fields + [f"{x_name} ({crs_authid(target)})", f"{y_name} ({crs_authid(target)})", "longitude (EPSG:4326)", "latitude (EPSG:4326)"]

    if context.get("dry_run"):
        return {"dry_run": True, "output_path": str(output), "columns": header, "feature_count": int(layer.featureCount()), "notes": notes}

    rows = 0
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(header)
        for feature in layer.getFeatures():
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            point = geometry.asPoint() if geometry_type == 0 and not geometry.isMultipart() else geometry.pointOnSurface().asPoint()
            target_point = to_target.transform(point) if to_target is not None else point
            geo_point = to_geo.transform(point)
            values = []
            for name in fields:
                value = feature[name]
                values.append("" if value is None or str(value) == "NULL" else value)
            writer.writerow(
                [feature.id()] + values
                + [round(target_point.x(), decimals), round(target_point.y(), decimals), round(geo_point.x(), 6), round(geo_point.y(), 6)]
            )
            rows += 1
    return {
        "layer_id": layer.id(), "layer": layer.name(), "output_path": str(output), "rows": rows, "columns": header,
        "crs": crs_authid(target), "delimiter": delimiter, "notes": notes,
    }
