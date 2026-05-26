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
DATA_ROOT = Path(os.environ.get("SIGMAI_TEST_DATA_DIR", ROOT.parent / ("Shapes pra " + "Teste")))
OUT_ROOT = ROOT / "test_outputs" / "sigmai_data_sources_regression"


def call(action: str, params: dict[str, Any] | None = None, dry_run: bool = False, expected_error: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = bridge_command(action, params or {}, dry_run=dry_run)
    except Exception as exc:
        response = {"ok": False, "errors": [{"code": "CLIENT_EXCEPTION", "message": str(exc)}]}
    codes = [err.get("code") for err in response.get("errors", [])]
    expected_block = expected_error is not None and expected_error in codes
    return {
        "action": action,
        "params": params or {},
        "dry_run": dry_run,
        "ok": bool(response.get("ok")),
        "expected_error": expected_error,
        "expected_block": expected_block,
        "status": "validated" if response.get("ok") or expected_block else "failed",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "data": response.get("data"),
        "errors": response.get("errors", []),
    }


def main() -> int:
    global OUT_ROOT
    parser = argparse.ArgumentParser(description="SIGMAI Data Sources/GPX Regression")
    parser.add_argument("--output-dir", default=str(OUT_ROOT))
    args = parser.parse_args()
    OUT_ROOT = Path(args.output_dir).resolve()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    gpx = next(iter(sorted(DATA_ROOT.rglob("*.gpx"))), None)
    kml = next(iter(sorted(DATA_ROOT.rglob("*.kml"))), None)
    shp = DATA_ROOT / "Municipios" / "SP_Municipios_2025.shp"
    records: list[dict[str, Any]] = []

    if shp.exists():
        records.append(call("inspect_data_source", {"path": str(shp)}))
    if kml and kml.exists():
        records.append(call("inspect_data_source", {"path": str(kml)}))
    if gpx and gpx.exists():
        records.extend([
            call("inspect_data_source", {"path": str(gpx)}),
            call("summarize_gpx_track", {"path": str(gpx)}),
            call("gpx_track_length", {"path": str(gpx)}),
            call("gpx_track_extent", {"path": str(gpx)}),
            call("load_gpx", {"path": str(gpx), "name": "SIGMAI GPX Regression"}, True),
            call("load_gpx", {"path": str(gpx), "name": "SIGMAI GPX Regression"}, False),
            call("list_gpx_layers", {}),
            call("map_gpx_track", {"path": str(gpx), "name": "SIGMAI GPX Map Regression"}, True),
        ])
    else:
        records.append({"action": "gpx_tests", "status": "skipped_no_gpx", "ok": True})

    records.extend([
        call("validate_service_url", {"url": "https://example.org/geoserver/wms?service=WMS"}),
        call("inspect_ogc_service", {"url": "https://example.org/geoserver/wms?service=WMS", "service_type": "WMS"}),
        call("list_ogc_connections", {}),
        call("load_wms_layer", {"url": "https://example.org/geoserver/wms?service=WMS"}, True),
        call("load_wms_layer", {"url": "https://example.org/geoserver/wms?service=WMS"}, False, expected_error="NETWORK_LOAD_NOT_ENABLED"),
        call("test_service_connection", {"url": "https://example.org/geoserver/wms"}, False, expected_error="NETWORK_CONFIRMATION_REQUIRED"),
        call("list_database_connections", {}),
        call("inspect_database_connection", {"name": "default"}),
        call("test_postgis_connection", {"name": "default"}, False, expected_error="DATABASE_CONNECTION_NOT_ENABLED"),
        call("load_postgis_layer", {"name": "default"}, True, expected_error="DATABASE_LOAD_NOT_ENABLED"),
        call("broken_data_source_report", {}),
        call("repair_data_source_path", {"layer_id": "dummy", "new_path": "dummy"}, True),
        call("repair_data_source_path", {"layer_id": "dummy", "new_path": "dummy"}, False, expected_error="REPAIR_DATA_SOURCE_NOT_ENABLED"),
    ])

    failed = [record for record in records if record.get("status") == "failed"]
    summary = {
        "records_total": len(records),
        "validated": len([record for record in records if record.get("status") in {"validated", "skipped_no_gpx"}]),
        "failed": len(failed),
        "expected_controlled_blocks": len([record for record in records if record.get("expected_block")]),
        "gpx_available": bool(gpx),
        "kml_available": bool(kml),
    }
    report = {
        "schema_version": "1.0",
        "generated_at": started_at,
        "regression_name": "SIGMAI Data Sources Regression",
        "summary": summary,
        "records": records,
        "failures": failed,
        "decision": "data_sources_foundation_validated" if not failed else "data_sources_need_fix",
        "limitation": "Network and database operations are intentionally blocked unless future credential-safe/network-confirmed workflows are implemented.",
    }
    (OUT_ROOT / "SIGMAI_DATA_SOURCES_REGRESSION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# SIGMAI Data Sources Regression", "", f"Generated at: {started_at}", "", "## Summary", "", f"- Records: {summary['validated']}/{summary['records_total']}", f"- Failed: {summary['failed']}", f"- Expected controlled blocks: {summary['expected_controlled_blocks']}", f"- GPX available: {summary['gpx_available']}", f"- Decision: {report['decision']}", "", "## Limitation", "", f"- {report['limitation']}"]
    (OUT_ROOT / "SIGMAI_DATA_SOURCES_REGRESSION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "RELATORIO_SIGMAI_DATA_SOURCES_VALIDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
