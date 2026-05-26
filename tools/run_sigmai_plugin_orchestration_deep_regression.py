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
OUT_ROOT = ROOT / "test_outputs" / "sigmai_plugin_orchestration_deep_regression"


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
    parser = argparse.ArgumentParser(description="SIGMAI Plugin Orchestration Deep Regression")
    parser.add_argument("--output-dir", default=str(OUT_ROOT))
    args = parser.parse_args()
    OUT_ROOT = Path(args.output_dir).resolve()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    adapter_report = str((OUT_ROOT / "topotrail_adapter_report.md").resolve())
    records = [
        call("list_qgis_plugins_extended", {}),
        call("list_processing_providers", {}),
        call("list_processing_algorithms", {"provider": "topotrail", "safe_only": True}),
        call("inspect_plugin_capabilities", {"plugin_name": "TopoTrail", "plugin_package": "TopoTrail"}),
        call("list_plugin_processing_algorithms", {"plugin_name": "TopoTrail", "plugin_package": "TopoTrail"}),
        call("get_plugin_algorithm_info", {"plugin_name": "TopoTrail", "plugin_package": "TopoTrail", "algorithm_id": "topotrail:topotrail"}),
        call("generate_plugin_adapter_report", {"plugin_name": "TopoTrail", "output_path": adapter_report, "confirm_overwrite": True}),
        call("run_plugin_algorithm_safe", {"algorithm_id": "topotrail:topotrail", "parameters": {}, "output": "TEMPORARY_OUTPUT"}, True),
        call("run_plugin_algorithm_safe", {"algorithm_id": "native:buffer", "parameters": {}, "output": "TEMPORARY_OUTPUT"}, True, expected_error="PLUGIN_ALGORITHM_NOT_ALLOWED"),
        call("inspect_plugin_capabilities", {"plugin_name": "NotAPlugin"}, False, expected_error="PLUGIN_NOT_FOUND"),
    ]
    outputs = [{"path": adapter_report, "exists": Path(adapter_report).exists(), "size": Path(adapter_report).stat().st_size if Path(adapter_report).exists() else 0}]
    failed = [record for record in records if record["status"] == "failed"]
    summary = {
        "records_total": len(records),
        "validated": len([record for record in records if record["status"] == "validated"]),
        "failed": len(failed),
        "expected_controlled_blocks": len([record for record in records if record["expected_block"]]),
        "outputs_non_empty": len([item for item in outputs if item["exists"] and item["size"] > 0]),
        "outputs_checked": len(outputs),
    }
    report = {
        "schema_version": "1.0",
        "generated_at": started_at,
        "regression_name": "SIGMAI Plugin Orchestration Deep Regression",
        "summary": summary,
        "records": records,
        "outputs": outputs,
        "failures": failed,
        "decision": "plugin_orchestration_foundation_validated" if not failed else "plugin_orchestration_needs_fix",
        "limitation": "Plugin execution remains allowlisted. Unknown plugin algorithms are blocked by default.",
    }
    (OUT_ROOT / "SIGMAI_PLUGIN_ORCHESTRATION_DEEP_REGRESSION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# SIGMAI Plugin Orchestration Deep Regression", "", f"Generated at: {started_at}", "", "## Summary", "", f"- Records: {summary['validated']}/{summary['records_total']}", f"- Failed: {summary['failed']}", f"- Expected controlled blocks: {summary['expected_controlled_blocks']}", f"- Outputs: {summary['outputs_non_empty']}/{summary['outputs_checked']} non-empty", f"- Decision: {report['decision']}", "", "## Limitation", "", f"- {report['limitation']}"]
    (OUT_ROOT / "SIGMAI_PLUGIN_ORCHESTRATION_DEEP_REGRESSION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "RELATORIO_SIGMAI_PLUGIN_ORCHESTRATION_DEEP_VALIDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
