from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sigmai import bridge_command  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "test_outputs" / "sigmai_atlas_report_regression"


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
        "warnings": response.get("warnings", []),
    }


def output_path(name: str) -> str:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    return str((OUT_ROOT / name).resolve())


def first_vector_layer() -> tuple[str, str]:
    response = bridge_command("list_layers", {})
    for layer in (response.get("data") or {}).get("layers", []):
        if layer.get("type") == "vector":
            return layer.get("id", ""), layer.get("name", "")
    raise RuntimeError("No vector layer loaded for atlas/report regression.")


def first_text_field(layer_id: str) -> str:
    response = bridge_command("list_fields", {"layer_id": layer_id})
    for field in (response.get("data") or {}).get("fields", []):
        if field.get("type", "").lower() in {"string", "text"} or field.get("type_name", "").lower() in {"string", "text"}:
            return field.get("name", "")
    fields = (response.get("data") or {}).get("fields", [])
    return fields[0].get("name", "") if fields else ""


def main() -> int:
    global OUT_ROOT
    parser = argparse.ArgumentParser(description="SIGMAI Atlas/Report Regression")
    parser.add_argument("--output-dir", default=str(OUT_ROOT))
    args = parser.parse_args()
    OUT_ROOT = Path(args.output_dir).resolve()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    try:
        layer_id, layer_name = first_vector_layer()
        title_field = first_text_field(layer_id)
    except Exception as exc:
        report = {"schema_version": "1.0", "generated_at": started_at, "summary": {"status": "SKIPPED_NO_VECTOR_LAYER", "error": str(exc)}}
        (OUT_ROOT / "SIGMAI_ATLAS_REPORT_REGRESSION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    atlas_name = "SIGMAI Regression Atlas"
    report_name = "SIGMAI Regression Technical Report"
    html_path = output_path("technical_report.html")
    pdf_path = output_path("technical_report_pdf_placeholder.json")

    records.extend([
        call("create_atlas", {"atlas_name": atlas_name, "coverage_layer_id": layer_id, "title_field": title_field}, True),
        call("create_atlas", {"atlas_name": atlas_name, "coverage_layer_id": layer_id, "title_field": title_field}, False),
        call("set_atlas_filter_expression", {"atlas_name": atlas_name, "expression": "1=1"}, True),
        call("set_atlas_filter_expression", {"atlas_name": atlas_name, "expression": "1=1"}, False),
        call("set_atlas_sort_expression", {"atlas_name": atlas_name, "expression": f'\"{title_field}\"' if title_field else "$id"}, True),
        call("set_atlas_sort_expression", {"atlas_name": atlas_name, "expression": f'\"{title_field}\"' if title_field else "$id"}, False),
        call("generate_map_book", {"coverage_layer_id": layer_id, "name_field": title_field, "limit": 5}),
        call("export_atlas_pdf", {"atlas_name": atlas_name, "output_path": output_path("atlas.pdf")}, True),
        call("export_atlas_images", {"atlas_name": atlas_name, "output_dir": str(OUT_ROOT)}, True),
        call("export_atlas_pdf", {"atlas_name": atlas_name, "output_path": output_path("atlas.pdf")}, False, expected_error="ATLAS_EXPORT_NOT_ENABLED"),
        call("create_report", {"report_name": report_name}, True),
        call("create_report", {"report_name": report_name}, False),
        call("add_report_section", {"report_name": report_name, "title": "Layer", "body": f"Coverage layer: {layer_name}"}, False),
        call("generate_analysis_report", {"report_name": "SIGMAI Analysis Report"}, False),
        call("export_report_html", {"report_name": report_name, "output_path": html_path, "confirm_overwrite": True}, False),
        call("export_report_pdf", {"report_name": report_name, "output_path": pdf_path}, True),
        call("export_report_pdf", {"report_name": report_name, "output_path": pdf_path}, False, expected_error="REPORT_PDF_NOT_ENABLED"),
    ])

    outputs = [
        {"path": html_path, "exists": Path(html_path).exists(), "size": Path(html_path).stat().st_size if Path(html_path).exists() else 0},
    ]
    failed = [record for record in records if record["status"] == "failed"]
    summary = {
        "records_total": len(records),
        "validated": len([record for record in records if record["status"] == "validated"]),
        "failed": len(failed),
        "expected_controlled_blocks": len([record for record in records if record["expected_block"]]),
        "outputs_checked": len(outputs),
        "outputs_non_empty": len([item for item in outputs if item["exists"] and item["size"] > 0]),
    }
    report = {
        "schema_version": "1.0",
        "generated_at": started_at,
        "regression_name": "SIGMAI Atlas/Report Regression",
        "layer_id": layer_id,
        "layer_name": layer_name,
        "summary": summary,
        "records": records,
        "outputs": outputs,
        "failures": failed,
        "decision": "atlas_report_foundation_validated" if not failed else "atlas_report_needs_fix",
        "limitation": "Formal QgsLayoutAtlas PDF/image batch export remains blocked until atlas runner/job integration is implemented.",
    }
    (OUT_ROOT / "SIGMAI_ATLAS_REPORT_REGRESSION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# SIGMAI Atlas/Report Regression",
        "",
        f"Generated at: {started_at}",
        "",
        "## Summary",
        "",
        f"- Records: {summary['validated']}/{summary['records_total']}",
        f"- Failed: {summary['failed']}",
        f"- Expected controlled blocks: {summary['expected_controlled_blocks']}",
        f"- Outputs: {summary['outputs_non_empty']}/{summary['outputs_checked']} non-empty",
        f"- Decision: {report['decision']}",
        "",
        "## Limitation",
        "",
        f"- {report['limitation']}",
    ]
    (OUT_ROOT / "SIGMAI_ATLAS_REPORT_REGRESSION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "RELATORIO_SIGMAI_ATLAS_REPORT_VALIDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
