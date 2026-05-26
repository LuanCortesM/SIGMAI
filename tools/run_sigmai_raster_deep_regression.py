from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sigmai import bridge_command  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
TEST_DATA_ROOT = Path(os.environ.get("SIGMAI_TEST_DATA_DIR", ROOT.parent / ("Shapes pra " + "Teste")))
OUT_ROOT = ROOT / "test_outputs" / "sigmai_raster_deep_regression"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def find_first(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def find_test_raster() -> Path | None:
    preferred = [
        TEST_DATA_ROOT / "22S465HN.tif",
        TEST_DATA_ROOT / "22S465SN.tif",
        TEST_DATA_ROOT / "22S465VN.tif",
        TEST_DATA_ROOT / "22S465ZN.tif",
    ]
    found = find_first(preferred)
    if found:
        return found
    rasters = sorted(TEST_DATA_ROOT.rglob("*.tif")) + sorted(TEST_DATA_ROOT.rglob("*.tiff"))
    return rasters[0] if rasters else None


def find_mask_vector() -> Path | None:
    preferred = [
        TEST_DATA_ROOT / "Municipios" / "SP_Municipios_2025.shp",
        TEST_DATA_ROOT / "Estados" / "BR_UF_2025.shp",
        TEST_DATA_ROOT / "Pais" / "BR_Pais_2025.shp",
    ]
    found = find_first(preferred)
    if found:
        return found
    vectors = sorted(TEST_DATA_ROOT.rglob("*.shp"))
    return vectors[0] if vectors else None


def output_path(name: str) -> str:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    return str((OUT_ROOT / name).resolve())


def record(action: str, params: dict[str, Any] | None = None, dry_run: bool = False, timeout_hint: int = 120) -> dict[str, Any]:
    start = time.perf_counter()
    params = params or {}
    try:
        response = bridge_command(action, params, dry_run=dry_run)
    except Exception as exc:
        response = {"ok": False, "errors": [{"code": "CLIENT_EXCEPTION", "message": str(exc)}]}
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    errors = response.get("errors") or []
    data = response.get("data") or {}
    warnings = response.get("warnings") or data.get("warnings") or []
    return {
        "action": action,
        "dry_run": dry_run,
        "params": params,
        "ok": bool(response.get("ok")),
        "elapsed_ms": elapsed_ms,
        "timeout_hint_seconds": timeout_hint,
        "status": "validated" if response.get("ok") else "failed",
        "warnings": warnings,
        "errors": errors,
        "data": response.get("data"),
        "raw_ok": response.get("ok"),
    }


def file_check(path: str) -> dict[str, Any]:
    p = Path(path)
    return {
        "path": str(p),
        "exists": p.exists(),
        "size": p.stat().st_size if p.exists() else 0,
        "non_empty": p.exists() and p.stat().st_size > 0,
    }


def shrink_extent(extent: dict[str, Any], factor: float = 0.2) -> str:
    xmin = float(extent["xmin"])
    xmax = float(extent["xmax"])
    ymin = float(extent["ymin"])
    ymax = float(extent["ymax"])
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    half_w = (xmax - xmin) * factor / 2
    half_h = (ymax - ymin) * factor / 2
    return f"{cx - half_w},{cx + half_w},{cy - half_h},{cy + half_h}"


def command_statuses(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        status = item.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def main() -> int:
    global OUT_ROOT
    parser = argparse.ArgumentParser(description="SIGMAI Raster Deep Regression")
    parser.add_argument("--output-dir", default=str(OUT_ROOT))
    parser.add_argument("--skip-heavy", action="store_true", help="Run only dry-run checks for heavier raster derivatives.")
    args = parser.parse_args()

    OUT_ROOT = Path(args.output_dir).resolve()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    raster = find_test_raster()
    mask = find_mask_vector()

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": started_at,
        "regression_name": "SIGMAI Raster Deep Regression",
        "test_data_root": str(TEST_DATA_ROOT),
        "raster_path": str(raster) if raster else None,
        "mask_vector_path": str(mask) if mask else None,
        "records": records,
        "outputs": outputs,
        "summary": {},
        "level8_raster_decision": "not_evaluated",
    }

    if not raster:
        report["summary"] = {"status": "SKIPPED_NO_TEST_RASTER"}
        write_json(OUT_ROOT / "SIGMAI_RASTER_DEEP_REGRESSION.json", report)
        return 0

    load = record("load_raster_layer", {"path": str(raster), "name": f"SIGMAI Raster Deep {raster.stem}"}, False)
    records.append(load)
    raster_layer_id = (load.get("data") or {}).get("layer_id")
    if not load["ok"] or not raster_layer_id:
        report["summary"] = {"status": "failed", "reason": "Could not load test raster."}
        write_json(OUT_ROOT / "SIGMAI_RASTER_DEEP_REGRESSION.json", report)
        return 1

    for action, params in [
        ("raster_info", {"layer_id": raster_layer_id}),
        ("raster_band_statistics", {"layer_id": raster_layer_id, "band": 1}),
        ("raster_metadata_report", {"layer_id": raster_layer_id}),
    ]:
        records.append(record(action, params, False))

    info = next((r for r in records if r["action"] == "raster_info" and r["ok"]), {})
    extent = ((info.get("data") or {}).get("extent") or {})
    subset_extent = shrink_extent(extent) if all(k in extent for k in ("xmin", "xmax", "ymin", "ymax")) else ""
    report["source_raster_info"] = info.get("data")
    report["subset_extent"] = subset_extent

    clipped_path = output_path("raster_clip_extent.tif")
    if subset_extent:
        records.append(record("raster_clip_by_extent", {"layer_id": raster_layer_id, "extent": subset_extent, "output": clipped_path, "confirm_overwrite": True}, True))
        records.append(record("raster_clip_by_extent", {"layer_id": raster_layer_id, "extent": subset_extent, "output": clipped_path, "confirm_overwrite": True}, False, 180))
        outputs.append(file_check(clipped_path))

    working_layer_id = raster_layer_id
    if Path(clipped_path).exists():
        clipped_load = record("load_raster_layer", {"path": clipped_path, "name": "SIGMAI Raster Deep clipped subset"}, False)
        records.append(clipped_load)
        working_layer_id = (clipped_load.get("data") or {}).get("layer_id") or raster_layer_id

    derivative_specs = [
        ("raster_hillshade", {"layer_id": working_layer_id, "output": output_path("raster_hillshade.tif"), "confirm_overwrite": True}),
        ("raster_slope", {"layer_id": working_layer_id, "output": output_path("raster_slope.tif"), "confirm_overwrite": True}),
        ("raster_aspect", {"layer_id": working_layer_id, "output": output_path("raster_aspect.tif"), "confirm_overwrite": True}),
        ("raster_contours", {"layer_id": working_layer_id, "interval": 20, "output": output_path("raster_contours.gpkg"), "confirm_overwrite": True}),
        ("raster_reproject", {"layer_id": working_layer_id, "target_crs": "EPSG:31983", "output": output_path("raster_reproject_31983.tif"), "confirm_overwrite": True}),
        ("raster_polygonize", {"layer_id": working_layer_id, "output": output_path("raster_polygonize.gpkg"), "confirm_overwrite": True}),
    ]

    for action, params in derivative_specs:
        records.append(record(action, params, True))
        if not args.skip_heavy:
            real = record(action, params, False, 240)
            records.append(real)
            out = params.get("output")
            if out:
                outputs.append(file_check(out))

    mask_layer_id = None
    if mask:
        mask_load = record("load_vector_layer", {"path": str(mask), "name": f"SIGMAI Raster Mask {mask.stem}"}, False)
        records.append(mask_load)
        mask_layer_id = (mask_load.get("data") or {}).get("layer_id")
    if mask_layer_id:
        clip_mask_params = {"layer_id": working_layer_id, "mask_layer_id": mask_layer_id, "output": output_path("raster_clip_mask.tif"), "confirm_overwrite": True}
        records.append(record("raster_clip_by_mask", clip_mask_params, True))
        if not args.skip_heavy:
            records.append(record("raster_clip_by_mask", clip_mask_params, False, 240))
            outputs.append(file_check(clip_mask_params["output"]))

    hillshade_path = output_path("raster_hillshade.tif")
    terrain_layer_id = working_layer_id
    if Path(hillshade_path).exists():
        terrain_load = record("load_raster_layer", {"path": hillshade_path, "name": "SIGMAI Raster Deep hillshade"}, False)
        records.append(terrain_load)
        terrain_layer_id = (terrain_load.get("data") or {}).get("layer_id") or working_layer_id

    terrain_map = output_path("raster_terrain_professional_map.png")
    terrain_map_record = record("generate_professional_map", {
        "layer_id": terrain_layer_id,
        "title": "SIGMAI Raster Terrain Deep Regression",
        "subtitle": "Hillshade / raster output validation",
        "output_path": terrain_map,
        "format": "png",
        "layout_template": "scientific_basic",
        "style_profile": "terrain_context",
        "legend_layers": [terrain_layer_id],
        "include_grid": True,
        "include_source": True,
        "data_source": "SIGMAI test data",
        "map_author": "",
        "public_mode": True,
        "confirm_overwrite": True,
        "apply_default_style": False,
    }, False, 180)
    records.append(terrain_map_record)
    outputs.append(file_check(terrain_map))
    terrain_layout_name = (terrain_map_record.get("data") or {}).get("layout_name")
    if terrain_layout_name:
        records.append(record("evaluate_map_quality", {"layout_name": terrain_layout_name, "output_path": terrain_map}, False))

    failed = [r for r in records if r.get("status") == "failed"]
    output_failures = [o for o in outputs if not o.get("non_empty")]
    warnings = [w for r in records for w in (r.get("warnings") or [])]
    summary = {
        "records_total": len(records),
        "validated": len([r for r in records if r.get("status") == "validated"]),
        "failed": len(failed),
        "outputs_checked": len(outputs),
        "outputs_non_empty": len([o for o in outputs if o.get("non_empty")]),
        "output_failures": len(output_failures),
        "status_counts": command_statuses(records),
        "warnings_count": len(warnings),
        "terrain_map": terrain_map,
    }
    report["summary"] = summary
    report["failures"] = failed
    report["output_failures"] = output_failures
    report["warnings"] = warnings
    report["level8_raster_decision"] = "raster_core_deep_validated" if not failed and not output_failures else "raster_core_needs_fix"

    json_path = OUT_ROOT / "SIGMAI_RASTER_DEEP_REGRESSION.json"
    write_json(json_path, report)

    md_lines = [
        "# SIGMAI Raster Deep Regression",
        "",
        f"Generated at: {started_at}",
        "",
        "## Summary",
        "",
        f"- Raster: `{raster}`",
        f"- Mask vector: `{mask}`",
        f"- Records total: {summary['records_total']}",
        f"- Validated: {summary['validated']}",
        f"- Failed: {summary['failed']}",
        f"- Outputs checked: {summary['outputs_checked']}",
        f"- Outputs non-empty: {summary['outputs_non_empty']}",
        f"- Decision: {report['level8_raster_decision']}",
        "",
        "## Outputs",
        "",
        "| Output | Exists | Size |",
        "|---|---:|---:|",
    ]
    for item in outputs:
        md_lines.append(f"| {item['path']} | {item['exists']} | {item['size']} |")
    md_lines.extend(["", "## Failures", ""])
    if failed:
        for item in failed:
            md_lines.append(f"- {item['action']}: {item.get('errors')}")
    else:
        md_lines.append("- None.")
    md_lines.extend(["", "## Warnings", ""])
    if warnings:
        for warning in warnings:
            md_lines.append(f"- {warning}")
    else:
        md_lines.append("- None.")
    md_path = OUT_ROOT / "SIGMAI_RASTER_DEEP_REGRESSION.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    root_report = ROOT / "RELATORIO_SIGMAI_RASTER_DEEP_VALIDATION.md"
    root_report.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed and not output_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
