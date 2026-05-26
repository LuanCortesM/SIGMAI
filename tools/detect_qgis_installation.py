from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "diagnostics"
JSON_REPORT = DIAGNOSTICS / "qgis_installation_detection.json"
MD_REPORT = DIAGNOSTICS / "qgis_installation_detection.md"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def candidate_roots() -> list[Path]:
    roots = []
    for base in [Path("C:/Program Files"), Path("C:/OSGeo4W"), Path("C:/OSGeo4W64")]:
        if base.name.lower().startswith("qgis") or base.name.lower().startswith("osgeo"):
            roots.append(base)
        if base.exists() and base.is_dir():
            roots.extend(path for path in base.glob("QGIS*") if path.is_dir())
    return sorted(set(roots), key=lambda p: str(p).lower())


def first_existing(paths: list[Path]) -> str:
    for path in paths:
        if path.exists():
            return str(path)
    return ""


def run_version(qgis_process: str) -> dict[str, Any]:
    if not qgis_process:
        return {}
    try:
        completed = subprocess.run([qgis_process, "--version"], capture_output=True, text=True, timeout=30)
        output = (completed.stdout or "") + (completed.stderr or "")
        return {"ok": completed.returncode == 0, "returncode": completed.returncode, "output": output.strip(), **parse_version_output(output)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def parse_version_output(output: str) -> dict[str, str]:
    fields = {}
    patterns = {
        "qgis_version": r"QGIS ([^\r\n]+)",
        "qt_version": r"Qt version ([^\r\n]+)",
        "python_version": r"Python version ([^\r\n]+)",
        "gdal_version": r"GDAL/OGR version ([^\r\n]+)",
        "proj_version": r"PROJ version ([^\r\n]+)",
        "geos_version": r"GEOS version ([^\r\n]+)",
        "sqlite_version": r"SQLite version ([^\r\n]+)",
        "os": r"OS ([^\r\n]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            fields[key] = match.group(1).strip()
    return fields


def inspect_root(root: Path) -> dict[str, Any]:
    bin_dir = root / "bin"
    apps_dir = root / "apps"
    qgis_process = first_existing(list(bin_dir.glob("qgis_process*.bat")) + list(bin_dir.glob("qgis_process*.exe")))
    info = {
        "root": str(root),
        "exists": root.exists(),
        "osgeo4w_bat": first_existing([root / "OSGeo4W.bat"]),
        "qgis_bat": first_existing(list(bin_dir.glob("qgis*.bat"))),
        "qgis_exe": first_existing(list(root.glob("**/qgis*.exe"))),
        "qgis_ltr_bin": first_existing(list(apps_dir.glob("qgis-ltr/bin/qgis-ltr-bin.exe")) + list(root.glob("**/qgis-ltr-bin.exe"))),
        "qgis_process": qgis_process,
        "python_qgis": first_existing(list(bin_dir.glob("python-qgis*.bat"))),
        "python_exe": first_existing([bin_dir / "python.exe"] + list(apps_dir.glob("Python*/python.exe"))),
    }
    info["version"] = run_version(qgis_process)
    return info


def detect() -> dict[str, Any]:
    installations = [inspect_root(root) for root in candidate_roots()]
    usable = [item for item in installations if item.get("qgis_process")]
    profile_plugins = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "QGIS" / "QGIS3" / "profiles" / "default" / "python" / "plugins"
    return {
        "generated_at": now(),
        "installations": installations,
        "selected": usable[0] if usable else None,
        "default_profile_plugins": str(profile_plugins),
        "sigmai_plugin_target": str(profile_plugins / "sigmai"),
    }


def write_markdown(report: dict[str, Any]) -> None:
    selected = report.get("selected") or {}
    lines = [
        "# QGIS Installation Detection",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## Selected Installation",
        "",
        f"- Root: `{selected.get('root', '')}`",
        f"- QGIS process: `{selected.get('qgis_process', '')}`",
        f"- Python QGIS: `{selected.get('python_qgis', '')}`",
        f"- OSGeo4W: `{selected.get('osgeo4w_bat', '')}`",
        f"- Version: `{(selected.get('version') or {}).get('qgis_version', '')}`",
        f"- Python: `{(selected.get('version') or {}).get('python_version', '')}`",
        "",
        "## Profile",
        "",
        f"- Default plugins folder: `{report.get('default_profile_plugins')}`",
        f"- SIGMAI target: `{report.get('sigmai_plugin_target')}`",
        "",
        "## Installations",
        "",
        "| Root | qgis_process | Python QGIS | Version |",
        "|---|---|---|---|",
    ]
    for item in report.get("installations", []):
        version = (item.get("version") or {}).get("qgis_version", "")
        lines.append(f"| `{item.get('root')}` | `{item.get('qgis_process')}` | `{item.get('python_qgis')}` | `{version}` |")
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    report = detect()
    JSON_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report)
    selected = report.get("selected")
    if selected:
        print(f"QGIS detected: {selected.get('root')}")
        print(f"Version: {(selected.get('version') or {}).get('qgis_version', 'unknown')}")
        print(f"Plugin target: {report['sigmai_plugin_target']}")
        return 0
    print("No usable QGIS installation detected.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
