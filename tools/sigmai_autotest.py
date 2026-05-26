from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "diagnostics"
JSON_REPORT = DIAGNOSTICS / "SIGMAI_AUTOTEST_REPORT.json"
MD_REPORT = DIAGNOSTICS / "SIGMAI_AUTOTEST_REPORT.md"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_step(name: str, args: list[str], allow_fail: bool = False) -> dict:
    completed = subprocess.run([sys.executable, *args], cwd=str(ROOT), capture_output=True, text=True)
    result = {
        "name": name,
        "args": [sys.executable, *args],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0 or allow_fail,
    }
    print(f"{name}: exit {completed.returncode}")
    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip())
    return result


def write_reports(report: dict) -> None:
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# SIGMAI Autotest Report", "", f"Generated at: `{report['generated_at']}`", ""]
    lines.extend(["## Steps", "", "| Step | Exit | OK |", "|---|---:|---:|"])
    for step in report["steps"]:
        lines.append(f"| `{step['name']}` | {step['returncode']} | {step['ok']} |")
    lines.extend(["", "## Recommendations", ""])
    lines.extend([f"- {item}" for item in report.get("recommendations", [])])
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-plugin", action="store_true")
    parser.add_argument("--launch-qgis", action="store_true")
    parser.add_argument("--wait-bridge", action="store_true")
    parser.add_argument("--run-integration", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--token", default=os.environ.get("SIGMAI_TOKEN", ""))
    args = parser.parse_args()

    if args.full:
        args.install_plugin = True
        args.wait_bridge = True
        args.run_integration = True

    steps = []
    steps.append(run_step("detect_qgis", ["tools/detect_qgis_installation.py"], allow_fail=False))
    if args.install_plugin:
        steps.append(run_step("install_plugin", ["tools/install_qgis_plugin.py"], allow_fail=False))
    if args.launch_qgis:
        steps.append(run_step("launch_qgis", ["tools/launch_qgis_for_tests.py"], allow_fail=True))
    steps.append(run_step("unit_tests", ["-m", "unittest", "discover", "tests"], allow_fail=False))
    if args.wait_bridge:
        wait_args = ["tools/wait_for_bridge.py"]
        if args.token:
            wait_args += ["--token", args.token]
        steps.append(run_step("wait_bridge", wait_args, allow_fail=True))
    if args.run_integration:
        integration_args = ["tools/run_sigmai_integration_tests.py"]
        if args.token:
            integration_args += ["--token", args.token]
        steps.append(run_step("integration_tests", integration_args, allow_fail=True))

    recommendations = []
    if any(step["name"] == "install_plugin" and step["returncode"] != 0 for step in steps):
        recommendations.append("Plugin installation was blocked. Run tools/install_qgis_plugin.py outside the sandbox or install the generated sigmai.zip in QGIS.")
    if any(step["name"] == "wait_bridge" and step["returncode"] != 0 for step in steps):
        recommendations.append("Open QGIS, enable SIGMAI, click Start Bridge, then rerun with --wait-bridge --run-integration --token TOKEN.")
    if any(step["name"] == "integration_tests" and step["returncode"] != 0 for step in steps):
        recommendations.append("Inspect diagnostics/integration_test_results.md for failed bridge commands.")
    report = {"generated_at": now(), "steps": steps, "recommendations": recommendations}
    write_reports(report)
    return 1 if any(not step["ok"] for step in steps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
