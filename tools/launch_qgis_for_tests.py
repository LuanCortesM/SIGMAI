from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from detect_qgis_installation import detect
from install_qgis_plugin import main as install_plugin


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "diagnostics"
REPORT = DIAGNOSTICS / "qgis_launch_report.json"


def main() -> int:
    install_code = install_plugin()
    report = detect()
    selected = report.get("selected") or {}
    qgis_launcher = selected.get("qgis_bat") or selected.get("qgis_ltr_bin") or selected.get("qgis_exe")
    payload = {"plugin_install_exit_code": install_code, "qgis_launcher": qgis_launcher, "launched": False}
    if not qgis_launcher:
        print("QGIS launcher not found. Install report was still generated.")
        REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 1

    try:
        process = subprocess.Popen([qgis_launcher], cwd=str(ROOT))
        payload.update({"launched": True, "pid": process.pid})
        print(f"QGIS launched with PID {process.pid}.")
        print("If the bridge does not start automatically, enable SIGMAI and click Start Bridge.")
        print("Then run: python tools\\wait_for_bridge.py --token TOKEN")
    except Exception as exc:
        payload.update({"error": f"{type(exc).__name__}: {exc}"})
        print(f"Could not launch QGIS: {exc}", file=sys.stderr)
        REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 1

    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
