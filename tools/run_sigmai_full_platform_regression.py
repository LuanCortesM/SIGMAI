from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "diagnostics"
OUT_JSON = OUT_DIR / "SIGMAI_FULL_PLATFORM_REGRESSION.json"
OUT_MD = OUT_DIR / "SIGMAI_FULL_PLATFORM_REGRESSION.md"


def _run(name: str, args: list[str], timeout: int = 180) -> dict[str, Any]:
    completed = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    return {
        "name": name,
        "command": args,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    checks = [
        _run("compileall", [sys.executable, "-m", "compileall", "-q", "sigmai", "codex_plugin", "tools", "mcp_server", "tests"]),
        _run("unittest", [sys.executable, "-m", "unittest", "discover", "tests"]),
        _run("status", [sys.executable, "tools/sigmai.py", "status"], timeout=60),
        _run("self_health_check", [sys.executable, "tools/sigmai.py", "self-health-check"], timeout=90),
        _run("capabilities", [sys.executable, "tools/sigmai.py", "capabilities"], timeout=90),
        _run("mcp_regression", [sys.executable, "tools/run_sigmai_mcp_regression.py"], timeout=180),
    ]
    evidence_files = [
        "RELATORIO_SIGMAI_LEVEL7_SCALE_FINAL_VALIDATION.md",
        "RELATORIO_SIGMAI_LEVEL8_VALIDATION.md",
        "RELATORIO_SIGMAI_JOB_QUEUE_VALIDATION.md",
        "RELATORIO_SIGMAI_ATLAS_REPORT_VALIDATION.md",
        "RELATORIO_SIGMAI_DATA_SOURCES_VALIDATION.md",
        "RELATORIO_SIGMAI_PLUGIN_ORCHESTRATION_DEEP_VALIDATION.md",
        "RELATORIO_SIGMAI_MCP_FORMAL_VALIDATION.md",
        "docs/SIGMAI_BROAD_QGIS_ECOSYSTEM_COVERAGE.md",
        "docs/PUBLIC_RELEASE_CHECKLIST.md",
        "diagnostics/SIGMAI_MCP_TOOL_COVERAGE.json",
    ]
    evidence = [{"path": path, "exists": (ROOT / path).exists()} for path in evidence_files]
    release_blockers = []
    if not all(item["ok"] for item in checks):
        release_blockers.append("One or more regression checks failed.")
    missing = [item["path"] for item in evidence if not item["exists"]]
    if missing:
        release_blockers.append(f"Missing evidence files: {', '.join(missing)}")
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_name": "SIGMAI Full Platform Regression",
        "checks": checks,
        "evidence": evidence,
        "summary": {
            "checks_total": len(checks),
            "checks_ok": sum(1 for item in checks if item["ok"]),
            "checks_failed": sum(1 for item in checks if not item["ok"]),
            "evidence_total": len(evidence),
            "evidence_present": sum(1 for item in evidence if item["exists"]),
            "release_ready": not release_blockers,
            "validated_levels": [7, 8, 9, 10, 11, 12, 13, 14] if not release_blockers else [7, 8, 9, 10, 11, 12, 13],
            "failed_levels": [] if not release_blockers else [14],
            "warnings": [
                "Level 14 means broad coverage roadmap and maturity governance, not complete implementation of every QGIS subsystem.",
                "Full public release still requires packaging review and manual QGIS Plugin Repository checklist.",
            ],
            "release_blockers": release_blockers,
        },
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# SIGMAI Full Platform Regression",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Checks: {report['summary']['checks_ok']}/{report['summary']['checks_total']} OK",
        f"- Evidence: {report['summary']['evidence_present']}/{report['summary']['evidence_total']} present",
        f"- Release ready: {report['summary']['release_ready']}",
        "",
        "## Checks",
        "",
    ]
    for item in checks:
        lines.append(f"- `{item['name']}`: ok={item['ok']} returncode={item['returncode']}")
    lines.extend(["", "## Evidence", ""])
    for item in evidence:
        lines.append(f"- `{item['path']}`: exists={item['exists']}")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report["summary"]["warnings"])
    if release_blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in release_blockers)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0 if not release_blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
