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
OUT_ROOT = ROOT / "test_outputs" / "sigmai_job_queue_regression"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def call(action: str, params: dict[str, Any] | None = None, dry_run: bool = False, expected_error: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = bridge_command(action, params or {}, dry_run=dry_run)
    except Exception as exc:
        response = {"ok": False, "errors": [{"code": "CLIENT_EXCEPTION", "message": str(exc)}]}
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
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
        "elapsed_ms": elapsed_ms,
        "data": response.get("data"),
        "errors": response.get("errors", []),
        "warnings": response.get("warnings", []),
    }


def wait_job(job_id: str, records: list[dict[str, Any]], timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        status = call("get_job_status", {"job_id": job_id})
        records.append(status)
        last = status
        job_status = ((status.get("data") or {}).get("status"))
        if job_status in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.2)
    return last


def main() -> int:
    global OUT_ROOT
    parser = argparse.ArgumentParser(description="SIGMAI Job Queue Regression")
    parser.add_argument("--output-dir", default=str(OUT_ROOT))
    args = parser.parse_args()
    OUT_ROOT = Path(args.output_dir).resolve()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc).isoformat()

    start_status = call("start_job", {"name": "status job", "action": "status", "params": {}, "dry_run": False})
    records.append(start_status)
    status_job_id = (start_status.get("data") or {}).get("job_id")
    if status_job_id:
        wait_job(status_job_id, records)
        records.append(call("get_job_result", {"job_id": status_job_id}))
        records.append(call("job_logs", {"job_id": status_job_id}))

    workflow_steps = [{"action": "status", "params": {}, "dry_run": False}]
    start_workflow = call("run_workflow_job", {"name": "job_workflow", "steps": workflow_steps})
    records.append(start_workflow)
    workflow_job_id = (start_workflow.get("data") or {}).get("job_id")
    if workflow_job_id:
        wait_job(workflow_job_id, records)
        records.append(call("get_job_result", {"job_id": workflow_job_id}))

    records.append(call("start_job", {"name": "unsafe real mutation", "action": "generate_professional_map", "params": {}, "dry_run": False}, expected_error="JOB_UNSAFE_ACTION_USE_DRY_RUN"))
    records.append(call("start_job", {"name": "unknown action", "action": "not_existing_command", "params": {}, "dry_run": True}, expected_error="ACTION_NOT_ALLOWED"))
    records.append(call("list_jobs", {"limit": 20}))
    records.append(call("clear_finished_jobs", {}))
    records.append(call("list_jobs", {"limit": 20}))

    failed = [record for record in records if record["status"] == "failed"]
    summary = {
        "records_total": len(records),
        "validated": len([record for record in records if record["status"] == "validated"]),
        "failed": len(failed),
        "expected_controlled_blocks": len([record for record in records if record["expected_block"]]),
    }
    report = {
        "schema_version": "1.0",
        "generated_at": started_at,
        "regression_name": "SIGMAI Job Queue Regression",
        "summary": summary,
        "records": records,
        "failures": failed,
        "decision": "job_queue_foundation_validated" if not failed else "job_queue_needs_fix",
        "limitation": "Initial job queue executes read-only actions and dry-run mutations only. Real long-running QGIS mutations require a future QgsTask-safe runner.",
    }
    write_json(OUT_ROOT / "SIGMAI_JOB_QUEUE_REGRESSION.json", report)
    lines = [
        "# SIGMAI Job Queue Regression",
        "",
        f"Generated at: {started_at}",
        "",
        "## Summary",
        "",
        f"- Records total: {summary['records_total']}",
        f"- Validated: {summary['validated']}",
        f"- Failed: {summary['failed']}",
        f"- Expected controlled blocks: {summary['expected_controlled_blocks']}",
        f"- Decision: {report['decision']}",
        "",
        "## Limitation",
        "",
        f"- {report['limitation']}",
        "",
        "## Failures",
        "",
    ]
    if failed:
        for item in failed:
            lines.append(f"- {item['action']}: {item['errors']}")
    else:
        lines.append("- None.")
    md = "\n".join(lines) + "\n"
    (OUT_ROOT / "SIGMAI_JOB_QUEUE_REGRESSION.md").write_text(md, encoding="utf-8")
    (ROOT / "RELATORIO_SIGMAI_JOB_QUEUE_VALIDATION.md").write_text(md, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
