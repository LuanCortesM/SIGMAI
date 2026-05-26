from __future__ import annotations

import fnmatch
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sigmai"
DIAGNOSTICS = ROOT / "diagnostics"
JSON_REPORT = DIAGNOSTICS / "plugin_installation_report.json"
MD_REPORT = DIAGNOSTICS / "plugin_installation_report.md"

EXCLUDES = {
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "logs",
    "diagnostics",
    "test_outputs",
    ".git",
    "*.tmp",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_target() -> Path:
    appdata = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
    return appdata / "QGIS" / "QGIS3" / "profiles" / "default" / "python" / "plugins" / "sigmai"


def excluded(path: Path) -> bool:
    parts = set(path.parts)
    if parts & {"__pycache__", "logs", "diagnostics", "test_outputs", ".git"}:
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDES)


def copy_plugin(target: Path) -> dict[str, Any]:
    copied = []
    skipped = []
    target.mkdir(parents=True, exist_ok=True)
    for source_path in SOURCE.rglob("*"):
        relative = source_path.relative_to(SOURCE)
        if excluded(relative):
            skipped.append(str(relative))
            continue
        target_path = target / relative
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied.append(str(relative))
    required = ["metadata.txt", "__init__.py", "plugin.py", "bridge_server.py", "qgis_actions", "icons"]
    missing = [item for item in required if not (target / item).exists()]
    return {"target": str(target), "copied": copied, "skipped": skipped, "missing_required": missing, "ok": not missing}


def write_reports(report: dict[str, Any]) -> None:
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Plugin Installation Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Source: `{report['source']}`",
        f"Target: `{report['target']}`",
        f"OK: `{report['ok']}`",
        "",
        "## Missing Required",
    ]
    lines.extend([f"- `{item}`" for item in report.get("missing_required", [])] or ["- None"])
    lines.extend(["", "## Copied Files", ""])
    lines.extend([f"- `{item}`" for item in report.get("copied", [])])
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    target = default_target()
    try:
        result = copy_plugin(target)
    except Exception as exc:
        result = {
            "target": str(target),
            "copied": [],
            "skipped": [],
            "missing_required": [],
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    report = {"generated_at": now(), "source": str(SOURCE), **result}
    write_reports(report)
    if not report["ok"]:
        print(f"Could not install SIGMAI plugin to: {target}")
        print(report.get("error", "Unknown installation error."))
        return 1
    print(f"Installed SIGMAI plugin to: {target}")
    if report["missing_required"]:
        print(f"Missing required items: {report['missing_required']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
