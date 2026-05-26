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
OUT_ROOT = ROOT / "test_outputs" / "sigmai_workflow_deep_regression"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def output_path(name: str) -> str:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    return str((OUT_ROOT / name).resolve())


def record(action: str, params: dict[str, Any] | None = None, dry_run: bool = False, expected_error: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    params = params or {}
    try:
        response = bridge_command(action, params, dry_run=dry_run)
    except Exception as exc:
        response = {"ok": False, "errors": [{"code": "CLIENT_EXCEPTION", "message": str(exc)}]}
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    error_codes = [err.get("code") for err in (response.get("errors") or [])]
    expected_block = expected_error is not None and expected_error in error_codes
    status = "validated" if response.get("ok") or expected_block else "failed"
    return {
        "action": action,
        "dry_run": dry_run,
        "params": params,
        "ok": bool(response.get("ok")),
        "expected_error": expected_error,
        "expected_block": expected_block,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "errors": response.get("errors") or [],
        "warnings": response.get("warnings") or [],
        "data": response.get("data"),
    }


def main() -> int:
    global OUT_ROOT
    parser = argparse.ArgumentParser(description="SIGMAI Workflow Deep Regression")
    parser.add_argument("--output-dir", default=str(OUT_ROOT))
    args = parser.parse_args()

    OUT_ROOT = Path(args.output_dir).resolve()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    template_path = output_path("municipal_professional_map_workflow.json")
    workflow_report_path = output_path("workflow_report.md")
    map_path = output_path("workflow_map.png")
    steps = [
        {"id": "status", "action": "status", "params": {}, "dry_run": False},
        {"id": "capabilities", "action": "get_capabilities", "params": {}, "dry_run": False},
        {"id": "report", "action": "generate_workflow_report", "params": {"output_path": workflow_report_path, "confirm_overwrite": True}, "dry_run": True},
        {"id": "map", "action": "generate_basic_map", "params": {"layer_id": "__LAYER_ID_FILLED_BY_USER__", "title": "Workflow placeholder map", "output_path": map_path}, "dry_run": True},
    ]
    safe_steps = steps[:3]
    bad_steps = [{"id": "bad", "action": "not_existing_command", "params": {}, "dry_run": True}]

    records: list[dict[str, Any]] = []
    records.append(record("plan_workflow", {"name": "level8_workflow_plan", "steps": safe_steps}))
    records.append(record("dry_run_workflow", {"name": "level8_workflow_dry_run", "steps": safe_steps}))
    records.append(record("save_workflow_template", {"name": "level8_workflow_template", "steps": safe_steps, "output_path": template_path, "confirm_overwrite": True}, True))
    records.append(record("save_workflow_template", {"name": "level8_workflow_template", "steps": safe_steps, "output_path": template_path, "confirm_overwrite": True}, False))
    records.append(record("list_workflow_templates", {}))
    records.append(record("run_workflow_template", {"path": template_path, "dry_run": True}, True))
    records.append(record("execute_workflow", {"name": "level8_workflow_execute_dry", "steps": safe_steps}, True))
    records.append(record("execute_workflow", {"name": "level8_workflow_execute_real", "steps": safe_steps}, False, expected_error="WORKFLOW_EXECUTION_NOT_ENABLED"))
    records.append(record("plan_workflow", {"name": "level8_workflow_bad_action", "steps": bad_steps}, False, expected_error="ACTION_NOT_ALLOWED"))
    records.append(record("generate_workflow_report", {"output_path": workflow_report_path, "confirm_overwrite": True}, True))
    records.append(record("generate_workflow_report", {"output_path": workflow_report_path, "confirm_overwrite": True}, False))

    outputs = [
        {"path": template_path, "exists": Path(template_path).exists(), "size": Path(template_path).stat().st_size if Path(template_path).exists() else 0},
        {"path": workflow_report_path, "exists": Path(workflow_report_path).exists(), "size": Path(workflow_report_path).stat().st_size if Path(workflow_report_path).exists() else 0},
    ]
    failed = [r for r in records if r["status"] == "failed"]
    blocked_expected = [r for r in records if r["expected_block"]]
    summary = {
        "records_total": len(records),
        "validated": len([r for r in records if r["status"] == "validated"]),
        "failed": len(failed),
        "expected_controlled_blocks": len(blocked_expected),
        "outputs_checked": len(outputs),
        "outputs_non_empty": len([o for o in outputs if o["exists"] and o["size"] > 0]),
    }
    decision = "workflow_foundation_partial_validated"
    limitation = "Real execute_workflow is intentionally disabled until the SIGMAI job runner is available."
    if failed:
        decision = "workflow_foundation_needs_fix"

    report = {
        "schema_version": "1.0",
        "generated_at": started_at,
        "regression_name": "SIGMAI Workflow Deep Regression",
        "summary": summary,
        "records": records,
        "outputs": outputs,
        "failures": failed,
        "decision": decision,
        "limitation": limitation,
        "level8_workflow_decision": "not_mature_until_execute_or_job_runner_is_available",
    }
    write_json(OUT_ROOT / "SIGMAI_WORKFLOW_DEEP_REGRESSION.json", report)

    lines = [
        "# SIGMAI Workflow Deep Regression",
        "",
        f"Generated at: {started_at}",
        "",
        "## Summary",
        "",
        f"- Records total: {summary['records_total']}",
        f"- Validated: {summary['validated']}",
        f"- Failed: {summary['failed']}",
        f"- Expected controlled blocks: {summary['expected_controlled_blocks']}",
        f"- Outputs non-empty: {summary['outputs_non_empty']}/{summary['outputs_checked']}",
        f"- Decision: {decision}",
        "",
        "## Limitation",
        "",
        f"- {limitation}",
        "- This is a safety-preserving limitation, not a crash.",
        "",
        "## Failures",
        "",
    ]
    if failed:
        for item in failed:
            lines.append(f"- {item['action']}: {item['errors']}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Outputs", "", "| Output | Exists | Size |", "|---|---:|---:|"])
    for item in outputs:
        lines.append(f"| {item['path']} | {item['exists']} | {item['size']} |")
    md = "\n".join(lines) + "\n"
    (OUT_ROOT / "SIGMAI_WORKFLOW_DEEP_REGRESSION.md").write_text(md, encoding="utf-8")
    (ROOT / "RELATORIO_SIGMAI_WORKFLOW_DEEP_VALIDATION.md").write_text(md, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
