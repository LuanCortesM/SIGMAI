"""Relações espaciais entre camadas, respondidas em texto e em número.

A descoberta de que o Parque Estadual das Carnaúbas fica no Ceará — e não
no Piauí, como a usuária pediu — veio de um assistente lendo os atributos
do KML. Foi sorte, não sistema. ``spatial_relationship`` responde de forma
direta e verificável: quanto de A está dentro de B, quais feições de B
tocam A, qual é a mais próxima e a que distância.

* área e comprimento são medidos no CRS da camada A (frações de uma mesma
  região se cancelam mesmo em coordenadas geográficas);
* distâncias são geodésicas (``QgsDistanceArea`` com o elipsoide do
  projeto, ou WGS 84), em metros, entre os pontos mais próximos das duas
  geometrias — não entre centroides.

É uma leitura: não cria camada nem altera o projeto.
"""

from __future__ import annotations

from typing import Any

from ..validators import ValidationError, require_param
from .common import crs_authid, layer_type_name, project

MAX_SUBJECT_FEATURES = 50
MAX_RESULTS = 100
#: Passos de busca pelos vizinhos mais próximos (múltiplos da diagonal do
#: retângulo envolvente de A), até desistir com nota.
SEARCH_STEPS = (2.0, 8.0, 32.0)
#: Trechos que denunciam um campo de nome (em vez de código).
NAME_FIELD_HINTS = ("nome", "name", "nm_", "_nm", "titulo", "título", "label", "descr", "toponim")


def _imports() -> dict[str, Any]:
    from qgis.core import (  # type: ignore
        QgsCoordinateTransform, QgsDistanceArea, QgsFeatureRequest, QgsGeometry, QgsProject, QgsRectangle,
    )

    return dict(
        QgsCoordinateTransform=QgsCoordinateTransform, QgsDistanceArea=QgsDistanceArea,
        QgsFeatureRequest=QgsFeatureRequest, QgsGeometry=QgsGeometry, QgsProject=QgsProject, QgsRectangle=QgsRectangle,
    )


def _vector_layer(layer_id: str, label: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        by_name = [c for c in project().mapLayers().values() if c.name() == layer_id]
        layer = by_name[0] if by_name else None
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", f"{label}: camada não encontrada: {layer_id}.", {label: layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", f"{label} precisa ser uma camada vetorial.", {label: layer_id})
    return layer


def _display_field(layer: Any, requested: str) -> str | None:
    names = [f.name() for f in layer.fields()]
    if requested:
        if requested not in names:
            raise ValidationError(
                "FIELD_NOT_FOUND", f"O campo {requested!r} não existe em {layer.name()!r}. Campos: {', '.join(names)}.",
                {"layer_id": layer.id(), "field": requested},
            )
        return requested
    # Campo de NOME antes de campo de CÓDIGO: "NM_MUN" antes de "CD_MUN",
    # "Nome_UC" antes de "Cod_CNUC". Sem um campo com cara de nome, o
    # primeiro campo de texto com conteúdo.
    text_fields = [f.name() for f in layer.fields() if f.typeName().lower() in ("string", "text", "varchar", "qstring")]
    ranked = sorted(text_fields, key=lambda n: (0 if any(h in n.lower() for h in NAME_FIELD_HINTS) else 1, text_fields.index(n)))
    try:
        for name in ranked:
            for feature in layer.getFeatures():
                value = feature[name]
                if value not in (None, "") and str(value) != "NULL":
                    return name
                break
    except Exception:
        pass
    return None


def _name(feature: Any, field: str | None) -> str:
    if field:
        try:
            value = feature[field]
            if value not in (None, "") and str(value) != "NULL":
                return str(value)
        except Exception:
            pass
    return f"fid {feature.id()}"


def _measure_setup(imports: dict[str, Any], crs: Any) -> Any:
    da = imports["QgsDistanceArea"]()
    da.setSourceCrs(crs, imports["QgsProject"].instance().transformContext())
    ellipsoid = ""
    try:
        ellipsoid = str(imports["QgsProject"].instance().ellipsoid() or "")
    except Exception:
        pass
    da.setEllipsoid(ellipsoid if ellipsoid and ellipsoid.upper() != "NONE" else "WGS84")
    return da


def _units_per_metre(imports: dict[str, Any], da: Any, bbox: Any) -> float:
    """Quantas unidades do CRS valem um metro, medido na diagonal do retângulo."""
    from qgis.core import QgsPointXY  # type: ignore

    x0, y0, x1, y1 = bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()
    if x1 - x0 <= 0 and y1 - y0 <= 0:
        x1 = x0 + 0.001  # ponto: mede um passo curto para leste
    units = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    try:
        metres = float(da.measureLine(QgsPointXY(x0, y0), QgsPointXY(x1, y1)))
    except Exception:
        metres = 0.0
    return units / metres if metres > 0 else 1.0


def _size(geometry: Any, geometry_type: int) -> float:
    if geometry_type == 2:
        return float(geometry.area())
    if geometry_type == 1:
        return float(geometry.length())
    return 1.0


def _shared(a: Any, b: Any, geometry_type: int) -> float:
    """Quanto de A (área, comprimento ou 0/1) está dentro de B."""
    if geometry_type == 0:
        return 1.0 if b.contains(a) or b.intersects(a) else 0.0
    part = a.intersection(b)
    if part is None or part.isEmpty():
        return 0.0
    return _size(part, geometry_type)


def spatial_relationship(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Contenção, interseção, vizinho mais próximo e distância entre A e B."""
    imports = _imports()
    subject = _vector_layer(require_param(params, "layer_id", str), "layer_id")
    other = _vector_layer(require_param(params, "other_layer_id", str), "other_layer_id")
    max_results = min(MAX_RESULTS, max(1, int(params.get("max_results") or 10)))
    display_field = _display_field(other, str(params.get("display_field") or "").strip())
    subject_field = _display_field(subject, str(params.get("subject_display_field") or "").strip())
    radius_m = float(params.get("radius_m") or 0.0)
    feature_id = params.get("feature_id")

    crs = subject.crs()
    if not crs.isValid():
        raise ValidationError("INVALID_CRS", f"A camada {subject.name()!r} não tem CRS válido.", {"layer_id": subject.id()})
    transform = None
    if other.crs().isValid() and crs_authid(other.crs()) != crs_authid(crs):
        transform = imports["QgsCoordinateTransform"](other.crs(), crs, imports["QgsProject"].instance())
    da = _measure_setup(imports, crs)
    geometry_type = int(subject.geometryType())
    other_type = int(other.geometryType())

    request = imports["QgsFeatureRequest"]()
    if feature_id is not None:
        request.setFilterFid(int(feature_id))
    subjects = list(subject.getFeatures(request))
    if feature_id is not None and not subjects:
        raise ValidationError("FEATURE_NOT_FOUND", f"feature_id {feature_id} não existe em {subject.name()!r}.", {"feature_id": feature_id})
    notes: list[str] = []
    if len(subjects) > MAX_SUBJECT_FEATURES:
        notes.append(
            f"{subject.name()!r} tem {len(subjects)} feições; só as {MAX_SUBJECT_FEATURES} primeiras foram analisadas. "
            "Passe feature_id para uma feição específica ou filtre a camada."
        )
        subjects = subjects[:MAX_SUBJECT_FEATURES]
    if crs.isGeographic():
        notes.append(
            "Frações de área/comprimento calculadas em coordenadas geográficas: válidas como proporção da mesma "
            "região; as distâncias são geodésicas em metros."
        )

    def other_features_in(rect: Any) -> list[tuple[Any, Any]]:
        req = imports["QgsFeatureRequest"]().setFilterRect(
            rect if transform is None else transform.transformBoundingBox(rect, imports["QgsCoordinateTransform"].ReverseTransform)
        )
        found = []
        for feature in other.getFeatures(req):
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            geometry = imports["QgsGeometry"](geometry)
            if transform is not None:
                geometry.transform(transform)
            found.append((feature, geometry))
        return found

    results = []
    for feature in subjects:
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        geometry = imports["QgsGeometry"](geometry)
        bbox = geometry.boundingBox()
        diagonal = max((bbox.width() ** 2 + bbox.height() ** 2) ** 0.5, 1e-9)
        total = _size(geometry, geometry_type)

        # Interseções: tudo que toca A.
        candidates = other_features_in(bbox)
        intersecting = []
        union_parts = []
        for candidate, candidate_geometry in candidates:
            if not candidate_geometry.intersects(geometry):
                continue
            shared = _shared(geometry, candidate_geometry, geometry_type)
            intersecting.append({
                "id": int(candidate.id()),
                "name": _name(candidate, display_field),
                "fraction_of_subject": round(shared / total, 4) if total > 0 else None,
            })
            if other_type == 2:
                union_parts.append(candidate_geometry)
        intersecting.sort(key=lambda entry: -(entry["fraction_of_subject"] or 0.0))
        inside_fraction = None
        if other_type == 2 and total > 0:
            covered = _shared(geometry, imports["QgsGeometry"].unaryUnion(union_parts), geometry_type) if union_parts else 0.0
            inside_fraction = round(min(1.0, covered / total), 4)

        # Vizinhos mais próximos entre os que NÃO tocam A.
        touching_ids = {entry["id"] for entry in intersecting}
        nearest: list[dict[str, Any]] = []
        if radius_m > 0:
            steps = [radius_m * _units_per_metre(imports, da, bbox)]
        else:
            steps = [diagonal * step for step in SEARCH_STEPS]
        for grown in steps:
            rect = imports["QgsRectangle"](bbox)
            rect.grow(grown)
            found = []
            for candidate, candidate_geometry in other_features_in(rect):
                if int(candidate.id()) in touching_ids:
                    continue
                line = geometry.shortestLine(candidate_geometry)
                if line is None or line.isEmpty():
                    continue
                try:
                    distance_m = float(da.measureLength(line))
                except Exception:
                    distance_m = float(line.length())
                if radius_m > 0 and distance_m > radius_m:
                    continue
                found.append({"id": int(candidate.id()), "name": _name(candidate, display_field), "distance_m": round(distance_m, 1)})
            found.sort(key=lambda entry: entry["distance_m"])
            if found or radius_m > 0:
                nearest = found[:max_results]
                break
        if not nearest and not intersecting:
            notes.append(f"Nenhuma feição de {other.name()!r} encontrada perto de {_name(feature, subject_field)!r} na busca progressiva.")

        summary_parts = []
        subject_name = _name(feature, subject_field)
        if inside_fraction is not None:
            summary_parts.append(f"{inside_fraction:.0%} de {subject_name!r} está dentro de {other.name()!r}")
        if intersecting:
            summary_parts.append("toca: " + ", ".join(e["name"] for e in intersecting[:max_results]))
        if nearest:
            closest = nearest[0]
            summary_parts.append(f"mais próxima sem tocar: {closest['name']} ({closest['distance_m'] / 1000:.1f} km)")
        results.append({
            "subject": {"id": int(feature.id()), "name": subject_name},
            "inside_fraction": inside_fraction,
            "intersecting": intersecting[:max_results],
            "nearest": nearest,
            "summary": "; ".join(summary_parts) if summary_parts else f"{subject_name!r} não toca nem tem vizinho de {other.name()!r} na busca.",
        })

    from .encoding import has_mojibake

    if any(has_mojibake(e["name"]) for r in results for e in (r["intersecting"] + r["nearest"] + [r["subject"]])):
        notes.append(
            "Há nomes com caracteres de substituição (�): a codificação de uma das camadas está errada; "
            "chame set_layer_encoding (ISO-8859-1 é o caso mais comum em shapefiles brasileiros sem .cpg)."
        )

    return {
        "layer": {"id": subject.id(), "name": subject.name(), "crs": crs_authid(crs)},
        "other_layer": {"id": other.id(), "name": other.name(), "crs": crs_authid(other.crs())},
        "display_field": display_field,
        "measured_in": crs_authid(crs),
        "distance_method": f"geodésica ({da.ellipsoid()})",
        "features": results,
        "notes": notes,
    }
