from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from ..security import normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param
from ..cartography.qtcompat import qt_enum
from .processing_bootstrap import resolve_algorithm, run_algorithm
from .common import crs_authid, layer_type_name, project, qgis_imports


PROCESSING_ALLOWLIST = {
    "native:buffer",
    "native:clip",
    "native:dissolve",
    "native:fixgeometries",
    "native:reprojectlayer",
    "native:multiparttosingleparts",
    "native:centroids",
    "native:intersection",
    "native:union",
    "native:difference",
    "native:extractbyattribute",
    "native:extractbylocation",
    "native:extractbyexpression",
    "native:countpointsinpolygon",
    "native:joinattributestable",
    "native:fieldcalculator",
    "gdal:cliprasterbyextent",
    "gdal:cliprasterbymasklayer",
    "gdal:warpreproject",
    "gdal:slope",
    "gdal:aspect",
    "gdal:hillshade",
    "gdal:contour",
    "gdal:polygonize",
    "topotrail:topotrail",
}


def _layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    return layer


def _vector_layer(layer_id: str):
    layer = _layer(layer_id)
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "This command requires a vector layer.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_LAYER", "Layer is invalid.", {"layer_id": layer_id})
    return layer


def _check_output(output: str, confirm_overwrite: bool) -> str:
    if output == "TEMPORARY_OUTPUT":
        return output
    output_path = normalize_output_path(output)
    try:
        reject_existing_path_without_confirmation(output_path, confirm_overwrite)
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc
    if not output_path.parent.exists():
        raise ValidationError("BAD_REQUEST", "Output directory does not exist.", {"path": str(output_path.parent)})
    return str(output_path)


def _processing_run(algorithm: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if algorithm not in PROCESSING_ALLOWLIST:
        raise ValidationError("PROCESSING_ALGORITHM_BLOCKED", "Algorithm is not in the SIGMAI Processing allowlist.", {"algorithm": algorithm})
    qgis_imports()  # só confirma que o PyQGIS está disponível; levanta se não estiver
    resolve_algorithm(algorithm)
    return run_algorithm(algorithm, parameters)


def _serialize_processing_result(result: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    output_layer_id = ""
    for key, value in result.items():
        if hasattr(value, "id") and hasattr(value, "name"):
            serialized[key] = {"layer_id": value.id(), "name": value.name(), "type": layer_type_name(value)}
            output_layer_id = value.id()
        else:
            serialized[key] = str(value) if isinstance(value, Path) else value
    if output_layer_id:
        serialized["output_layer_id"] = output_layer_id
    return serialized


def _crs_payload(layer: Any) -> dict[str, Any]:
    crs = layer.crs() if hasattr(layer, "crs") else None
    return {
        "authid": crs_authid(crs),
        "valid": bool(crs and crs.isValid()),
        "geographic": bool(crs and crs.isValid() and crs.isGeographic()),
    }


def diagnose_crs(params: dict[str, Any], context: dict[str, Any]):
    qgs_project = project()
    project_crs = qgs_project.crs()
    project_authid = crs_authid(project_crs)
    project_geographic = bool(project_crs.isValid() and project_crs.isGeographic())
    layers = []
    warnings: list[str] = []
    recommendations: list[str] = []
    for layer in qgs_project.mapLayers().values():
        crs_info = _crs_payload(layer)
        mismatched = bool(project_authid and crs_info["authid"] and crs_info["authid"] != project_authid)
        item = {
            "layer_id": layer.id(),
            "layer_name": layer.name(),
            "layer_type": layer_type_name(layer),
            "layer_crs": crs_info["authid"],
            "layer_crs_valid": crs_info["valid"],
            "missing_crs": not bool(crs_info["authid"]),
            "invalid_crs": not crs_info["valid"],
            "mismatched_crs": mismatched,
            "geographic": crs_info["geographic"],
        }
        layers.append(item)
        if item["missing_crs"] or item["invalid_crs"]:
            warnings.append(f"Layer '{layer.name()}' has missing or invalid CRS.")
            recommendations.append(f"Assign or define the correct CRS for layer '{layer.name()}' before spatial analysis.")
        if mismatched:
            warnings.append(f"Layer '{layer.name()}' CRS differs from project CRS.")
            recommendations.append(f"Consider reprojecting '{layer.name()}' to {project_authid} for consistent analysis.")
    if project_geographic:
        warnings.append("Project CRS is geographic. Metric operations such as buffer, area and distance may be incorrect.")
        recommendations.append("Use a projected CRS appropriate for the study area before metric analysis.")
    return {
        "project_crs": project_authid,
        "project_crs_valid": bool(project_crs.isValid()),
        "project_crs_geographic": project_geographic,
        "layers": layers,
        "warnings": warnings,
        "recommendations": sorted(set(recommendations)),
    }


def validate_geometries(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    max_features = int(params.get("max_features", 500))
    max_seconds = float(params.get("max_seconds", 3.0))
    deep = bool(params.get("deep", False))
    if max_features <= 0:
        raise ValidationError("BAD_REQUEST", "max_features must be greater than zero.", {"max_features": max_features})
    if max_seconds <= 0:
        raise ValidationError("BAD_REQUEST", "max_seconds must be greater than zero.", {"max_seconds": max_seconds})
    invalid_ids: list[Any] = []
    empty_ids: list[Any] = []
    null_ids: list[Any] = []
    total_checked = 0
    timed_out = False
    started = time.perf_counter()
    for feature in layer.getFeatures():
        if total_checked >= max_features:
            break
        if (time.perf_counter() - started) > max_seconds:
            timed_out = True
            break
        total_checked += 1
        geometry = feature.geometry()
        if geometry is None:
            null_ids.append(feature.id())
            continue
        if geometry.isNull():
            null_ids.append(feature.id())
            continue
        if geometry.isEmpty():
            empty_ids.append(feature.id())
            continue
        if deep:
            try:
                errors = geometry.validateGeometry()
            except Exception:
                errors = []
            if errors:
                invalid_ids.append(feature.id())
    feature_count = int(layer.featureCount())
    reached_limit = feature_count > total_checked or timed_out
    recommendations = []
    if invalid_ids or empty_ids or null_ids:
        recommendations.append("Run fix_geometries before spatial analysis.")
    if reached_limit:
        recommendations.append("Increase max_features/max_seconds or run a dedicated Processing validation for a complete scan.")
    if not deep:
        recommendations.append("Deep topology validation was not run by default to keep SIGMAI responsive. Pass deep=true for sampled topology checks.")
    return {
        "layer_id": layer.id(),
        "layer_name": layer.name(),
        "feature_count": feature_count,
        "total_checked": total_checked,
        "max_features": max_features,
        "max_seconds": max_seconds,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "deep_validation": deep,
        "timed_out": timed_out,
        "invalid_count": len(invalid_ids),
        "empty_geometry_count": len(empty_ids),
        "null_geometry_count": len(null_ids),
        "invalid_feature_ids_sample": invalid_ids[:50],
        "empty_feature_ids_sample": empty_ids[:50],
        "null_feature_ids_sample": null_ids[:50],
        "reached_limit": reached_limit,
        "recommendations": recommendations,
    }


def fix_geometries(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    parameters = {"INPUT": layer, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:fixgeometries", "parameters": {"INPUT": layer.id(), "OUTPUT": output}, "changes": ["Create a fixed-geometry output layer."]}
    result = _processing_run("native:fixgeometries", parameters)
    return {"algorithm": "native:fixgeometries", "result": _serialize_processing_result(result)}


def buffer(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    distance = float(params.get("distance", 0))
    segments = int(params.get("segments", 8))
    if distance <= 0:
        raise ValidationError("BAD_REQUEST", "distance must be greater than zero.", {"distance": distance})
    if segments <= 0:
        raise ValidationError("BAD_REQUEST", "segments must be greater than zero.", {"segments": segments})
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    warnings = []
    if layer.crs().isValid() and layer.crs().isGeographic():
        warnings.append("Input layer CRS is geographic. Buffer distance is not metric unless the CRS units are appropriate.")
    parameters = {
        "INPUT": layer,
        "DISTANCE": distance,
        "SEGMENTS": segments,
        "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0,
        "MITER_LIMIT": 2,
        "DISSOLVE": bool(params.get("dissolve", False)),
        "OUTPUT": output,
    }
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:buffer", "parameters": {"INPUT": layer.id(), **{k: v for k, v in parameters.items() if k != "INPUT"}}, "warnings": warnings}
    result = _processing_run("native:buffer", parameters)
    return {"algorithm": "native:buffer", "warnings": warnings, "result": _serialize_processing_result(result)}


def clip(params: dict[str, Any], context: dict[str, Any]):
    input_layer = _vector_layer(require_param(params, "input_layer_id", str))
    overlay_layer = _vector_layer(require_param(params, "overlay_layer_id", str))
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    warnings = []
    if crs_authid(input_layer.crs()) != crs_authid(overlay_layer.crs()):
        warnings.append("Input and overlay layer CRS differ. Reproject before clipping for safer results.")
    parameters = {"INPUT": input_layer, "OVERLAY": overlay_layer, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:clip", "parameters": {"INPUT": input_layer.id(), "OVERLAY": overlay_layer.id(), "OUTPUT": output}, "warnings": warnings}
    result = _processing_run("native:clip", parameters)
    return {"algorithm": "native:clip", "warnings": warnings, "result": _serialize_processing_result(result)}


def dissolve(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    fields = params.get("fields", [])
    if not isinstance(fields, list):
        raise ValidationError("BAD_REQUEST", "fields must be a list.", {"fields": fields})
    field_names = {field.name() for field in layer.fields()}
    missing = [field for field in fields if field not in field_names]
    if missing:
        raise ValidationError("FIELD_NOT_FOUND", "One or more dissolve fields do not exist.", {"missing_fields": missing})
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    parameters = {"INPUT": layer, "FIELD": fields, "SEPARATE_DISJOINT": False, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:dissolve", "parameters": {"INPUT": layer.id(), "FIELD": fields, "OUTPUT": output}}
    result = _processing_run("native:dissolve", parameters)
    return {"algorithm": "native:dissolve", "result": _serialize_processing_result(result)}


def reproject_layer(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    target_crs = require_param(params, "target_crs", str)
    try:
        from qgis.core import QgsCoordinateReferenceSystem  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc
    crs = QgsCoordinateReferenceSystem(target_crs)
    if not crs.isValid():
        raise ValidationError("INVALID_CRS", "target_crs is invalid.", {"target_crs": target_crs})
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    parameters = {"INPUT": layer, "TARGET_CRS": crs, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:reprojectlayer", "parameters": {"INPUT": layer.id(), "TARGET_CRS": target_crs, "OUTPUT": output}}
    result = _processing_run("native:reprojectlayer", parameters)
    return {"algorithm": "native:reprojectlayer", "result": _serialize_processing_result(result)}


def export_layer(params: dict[str, Any], context: dict[str, Any]):
    layer = _layer(require_param(params, "layer_id", str))
    output_path = _check_output(require_param(params, "output_path", str), bool(params.get("confirm_overwrite")))
    fmt = str(params.get("format", "GPKG")).upper()
    driver_by_format = {"GPKG": "GPKG", "GEOJSON": "GeoJSON", "SHAPEFILE": "ESRI Shapefile", "SHP": "ESRI Shapefile"}
    if layer_type_name(layer) != "vector":
        raise ValidationError("UNSUPPORTED_LAYER_EXPORT", "export_layer currently supports vector layers only.", {"layer_type": layer_type_name(layer)})
    driver = driver_by_format.get(fmt)
    if not driver:
        raise ValidationError("UNSUPPORTED_EXPORT_FORMAT", "Unsupported vector export format.", {"format": fmt, "supported": sorted(driver_by_format)})
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer.id(), "output_path": output_path, "format": fmt, "driver": driver, "changes": ["Write a new exported vector dataset without modifying the source layer."]}
    try:
        from qgis.core import QgsCoordinateTransformContext, QgsVectorFileWriter  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver
    options.fileEncoding = "UTF-8"
    result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, output_path, QgsCoordinateTransformContext(), options)
    error_code = result[0] if isinstance(result, tuple) else result
    if error_code != qt_enum(QgsVectorFileWriter, "WriterError", "NoError"):
        raise ValidationError("EXPORT_FAILED", "QGIS failed to export layer.", {"result": str(result)})
    return {"layer_id": layer.id(), "output_path": output_path, "format": fmt, "driver": driver}


def intersection(params: dict[str, Any], context: dict[str, Any]):
    input_layer = _vector_layer(require_param(params, "input_layer_id", str))
    overlay_layer = _vector_layer(require_param(params, "overlay_layer_id", str))
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    parameters = {"INPUT": input_layer, "OVERLAY": overlay_layer, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:intersection", "parameters": {"INPUT": input_layer.id(), "OVERLAY": overlay_layer.id(), "OUTPUT": output}}
    result = _processing_run("native:intersection", parameters)
    return {"algorithm": "native:intersection", "result": _serialize_processing_result(result)}


def union(params: dict[str, Any], context: dict[str, Any]):
    input_layer = _vector_layer(require_param(params, "input_layer_id", str))
    overlay_layer = _vector_layer(require_param(params, "overlay_layer_id", str))
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    parameters = {"INPUT": input_layer, "OVERLAY": overlay_layer, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:union", "parameters": {"INPUT": input_layer.id(), "OVERLAY": overlay_layer.id(), "OUTPUT": output}}
    result = _processing_run("native:union", parameters)
    return {"algorithm": "native:union", "result": _serialize_processing_result(result)}


def difference(params: dict[str, Any], context: dict[str, Any]):
    input_layer = _vector_layer(require_param(params, "input_layer_id", str))
    overlay_layer = _vector_layer(require_param(params, "overlay_layer_id", str))
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    parameters = {"INPUT": input_layer, "OVERLAY": overlay_layer, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:difference", "parameters": {"INPUT": input_layer.id(), "OVERLAY": overlay_layer.id(), "OUTPUT": output}}
    result = _processing_run("native:difference", parameters)
    return {"algorithm": "native:difference", "result": _serialize_processing_result(result)}


def centroids(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    parameters = {"INPUT": layer, "ALL_PARTS": bool(params.get("all_parts", False)), "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:centroids", "parameters": {"INPUT": layer.id(), "OUTPUT": output}}
    result = _processing_run("native:centroids", parameters)
    return {"algorithm": "native:centroids", "result": _serialize_processing_result(result)}


def multipart_to_singleparts(params: dict[str, Any], context: dict[str, Any]):
    layer = _vector_layer(require_param(params, "layer_id", str))
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    parameters = {"INPUT": layer, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:multiparttosingleparts", "parameters": {"INPUT": layer.id(), "OUTPUT": output}}
    result = _processing_run("native:multiparttosingleparts", parameters)
    return {"algorithm": "native:multiparttosingleparts", "result": _serialize_processing_result(result)}


def count_points_in_polygon(params: dict[str, Any], context: dict[str, Any]):
    polygons = _vector_layer(require_param(params, "polygon_layer_id", str))
    points = _vector_layer(require_param(params, "point_layer_id", str))
    output = _check_output(params.get("output", "TEMPORARY_OUTPUT"), bool(params.get("confirm_overwrite")))
    field_name = str(params.get("count_field", "NUMPOINTS"))
    parameters = {"POLYGONS": polygons, "POINTS": points, "FIELD": field_name, "OUTPUT": output}
    if context.get("dry_run"):
        return {"dry_run": True, "algorithm": "native:countpointsinpolygon", "parameters": {"POLYGONS": polygons.id(), "POINTS": points.id(), "FIELD": field_name, "OUTPUT": output}}
    result = _processing_run("native:countpointsinpolygon", parameters)
    return {"algorithm": "native:countpointsinpolygon", "result": _serialize_processing_result(result)}


#: Marca da camada de locais: o id da camada de registros de que ela saiu. Não
#: é a marca de anotação (DERIVED_FROM_PROPERTY, das divisas e nomes): com
#: ela os locais saíam da linha de crédito como desenho, e a fonte do GBIF,
#: com o DOI que a licença manda citar, sumia do rodapé.
SITES_OF_PROPERTY = "sigmai/sites_of"

#: Casas decimais com que coordenadas viram o mesmo local em count_points_by_site:
#: em graus, 5 casas são cerca de 1 m no equador; em metros, 0 casas é 1 m.
SITE_DECIMALS_GEOGRAPHIC = 5
SITE_DECIMALS_PROJECTED = 0


def _scale_denominator(value: Any) -> float | None:
    """300000 de 300000, "300000" ou "1:300.000" (o que compose_map escreve); None se vazio."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("scale não é verdadeiro/falso")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.startswith("1:"):
        text = "".join(ch for ch in text[2:] if ch.isdigit())
    return float(text)


def _metres_per_unit(crs: Any, latitudes: list[float]) -> tuple[float, float]:
    """Metros por unidade da camada, em x e em y: 1 num sistema métrico; em graus, na latitude média dos dados."""
    if crs.isGeographic():
        import math

        latitude = math.radians(sum(latitudes) / len(latitudes)) if latitudes else 0.0
        return 111_320.0 * max(0.05, math.cos(latitude)), 110_574.0
    try:
        from qgis.core import Qgis, QgsUnitTypes  # type: ignore

        from ..cartography.qtcompat import distance_unit

        factor = float(QgsUnitTypes.fromUnitToUnitFactor(crs.mapUnits(), distance_unit(Qgis, QgsUnitTypes, "Meters")))
        if factor > 0:
            return factor, factor
    except Exception:
        pass
    return 1.0, 1.0


def count_points_by_site(params: dict[str, Any], context: dict[str, Any]):
    """Um ponto por local, com quantos pontos da camada caem nele.

    Dados de ocorrência repetem coordenadas: os 362.210 registros do GBIF no
    PARNA do Itatiaia estão em 11.742 coordenadas distintas, e uma delas tem
    54.009. Num mapa de pontos esse local aparece igual a um com um registro
    só (CART076). Os locais, com a contagem, vão para
    apply_proportional_symbol_style. Grava um GeoPackage novo e não altera a
    camada de origem. A camada nova é dado, e não anotação: tem a sua fonte
    em data_source e guarda em ``SITES_OF_PROPERTY`` o id dos registros.

    Com ``scale`` (o denominador da escala do mapa, que sigmai_plan_map
    informa), os locais a menos de ``min_spacing_mm`` no papel viram um só
    (``pointdensity.merge_sites``): sem isso, a 1:300.000, os 11.224 locais a
    1 m do Itatiaia se amontoavam, e 79 % dos círculos caíam sobre outros.
    """
    layer = _vector_layer(require_param(params, "layer_id", str))
    imports = qgis_imports()
    from qgis.core import QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsVectorLayer  # type: ignore

    from ..cartography.qtcompat import geometry_type

    imports.update(QgsFeature=QgsFeature, QgsFeatureRequest=QgsFeatureRequest, QgsGeometry=QgsGeometry,
                   QgsPointXY=QgsPointXY, QgsVectorLayer=QgsVectorLayer)

    if layer.geometryType() != geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Point"):
        raise ValidationError("POINT_LAYER_REQUIRED", "count_points_by_site precisa de uma camada de pontos.", {"layer_id": layer.id()})
    output_path = _check_output(require_param(params, "output_path", str), bool(params.get("confirm_overwrite")))
    if Path(output_path).suffix.lower() != ".gpkg":
        raise ValidationError("BAD_REQUEST", "output_path precisa terminar em .gpkg.", {"output_path": output_path})
    geographic = bool(layer.crs().isGeographic())
    default = SITE_DECIMALS_GEOGRAPHIC if geographic else SITE_DECIMALS_PROJECTED
    decimals = int(params.get("decimals", default))
    if not -3 <= decimals <= 9:
        raise ValidationError("BAD_REQUEST", "decimals vai de -3 a 9.", {"decimals": decimals})
    count_field = str(params.get("count_field") or "records").strip()
    if not count_field.replace("_", "").isalnum():
        raise ValidationError("BAD_REQUEST", "count_field aceita letras, números e _.", {"count_field": count_field})
    layer_name = str(params.get("layer_name") or f"{layer.name()} (sites)").strip()
    from ..cartography.pointdensity import SITE_SPACING_MM, merge_sites

    try:
        scale = _scale_denominator(params.get("scale"))
        spacing = float(params.get("min_spacing_mm", SITE_SPACING_MM))
    except (TypeError, ValueError) as exc:
        raise ValidationError("BAD_REQUEST", "scale e min_spacing_mm precisam ser números.",
                              {"scale": params.get("scale"), "min_spacing_mm": params.get("min_spacing_mm")}) from exc
    if scale is not None and not 1 <= scale <= 1e9:
        raise ValidationError("BAD_REQUEST", "scale é o denominador da escala do mapa (300000 para 1:300.000).", {"scale": scale})
    if not 0 < spacing <= 20:
        raise ValidationError("BAD_REQUEST", "min_spacing_mm vai de 0 a 20.", {"min_spacing_mm": spacing})

    request = imports["QgsFeatureRequest"]().setNoAttributes()
    counts: dict[tuple[float, float], int] = {}
    for feature in layer.getFeatures(request):
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        for point in (geometry.asMultiPoint() if geometry.isMultipart() else [geometry.asPoint()]):
            key = (round(point.x(), decimals), round(point.y(), decimals))
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        raise ValidationError("EMPTY_LAYER", "A camada não tem pontos.", {"layer_id": layer.id()})
    distinct = len(counts)
    if scale is not None:
        x_metres, y_metres = _metres_per_unit(layer.crs(), [key[1] for key in counts])
        merged = merge_sites([(x, y, n) for (x, y), n in counts.items()], spacing * scale / 1000.0, x_metres, y_metres)
        counts = {(x, y): n for x, y, n in merged}
    summary = {"source_layer_id": layer.id(), "output_path": output_path, "decimals": decimals,
               "count_field": count_field, "records": sum(counts.values()), "sites": len(counts),
               "max_records_per_site": max(counts.values()), "distinct_coordinates": distinct}
    if scale is not None:
        summary.update(scale=int(scale), min_spacing_mm=spacing)
    else:
        summary["note"] = ("Sem scale, cada coordenada é um local. Para um mapa, passe scale (o denominador da escala, "
                           "que sigmai_plan_map informa): locais a menos de 1 mm no papel se sobrepõem.")
    if context.get("dry_run"):
        return {"dry_run": True, **summary, "changes": ["Grava um GeoPackage novo com um ponto por local e o adiciona ao projeto."]}

    sites = imports["QgsVectorLayer"](f"Point?crs={crs_authid(layer.crs())}&field={count_field}:integer", layer_name, "memory")
    features = []
    for (x, y), count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        feature = imports["QgsFeature"](sites.fields())
        feature.setGeometry(imports["QgsGeometry"].fromPointXY(imports["QgsPointXY"](x, y)))
        feature.setAttribute(count_field, count)
        features.append(feature)
    sites.dataProvider().addFeatures(features)
    sites.updateExtents()
    from qgis.core import QgsVectorFileWriter  # type: ignore

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "sites"
    options.fileEncoding = "UTF-8"
    result = QgsVectorFileWriter.writeAsVectorFormatV3(sites, output_path, project().transformContext(), options)
    error_code = result[0] if isinstance(result, tuple) else result
    if error_code != qt_enum(QgsVectorFileWriter, "WriterError", "NoError"):
        raise ValidationError("WRITE_FAILED", "Não foi possível gravar os locais.", {"result": str(result), "path": output_path})
    persisted = imports["QgsVectorLayer"](f"{output_path}|layername=sites", layer_name, "ogr")
    if not persisted.isValid():
        raise ValidationError("WRITE_FAILED", "O GeoPackage gravado não pôde ser lido de volta.", {"path": output_path})
    persisted.setCustomProperty(SITES_OF_PROPERTY, str(layer.id()))
    project().addMapLayer(persisted)
    return {**summary, "layer_id": persisted.id(), "name": persisted.name()}
