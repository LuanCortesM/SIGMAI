from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "diagnostics"
JSON_REPORT = DIAGNOSTICS / "qgis_environment_report.json"
MD_REPORT = DIAGNOSTICS / "qgis_environment_report.md"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_call(fn, default=None):
    try:
        return fn()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def import_status(name: str) -> dict[str, Any]:
    try:
        module = __import__(name, fromlist=["*"])
        return {"available": True, "module": getattr(module, "__name__", name)}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def collect() -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": now(),
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "prefix": sys.prefix,
            "path": sys.path,
        },
        "environment": {
            key: os.environ.get(key, "")
            for key in [
                "PATH",
                "PYTHONPATH",
                "QGIS_PREFIX_PATH",
                "QT_PLUGIN_PATH",
                "GDAL_DATA",
                "PROJ_LIB",
                "OSGEO4W_ROOT",
            ]
        },
        "imports": {
            "qgis.core": import_status("qgis.core"),
            "qgis.gui": import_status("qgis.gui"),
            "qgis.PyQt": import_status("qgis.PyQt"),
            "processing": import_status("processing"),
            "osgeo.gdal": import_status("osgeo.gdal"),
        },
    }

    try:
        from qgis.core import Qgis, QgsApplication, QgsProject  # type: ignore

        report["qgis"] = {
            "version": Qgis.QGIS_VERSION,
            "version_int": Qgis.QGIS_VERSION_INT,
            "prefix_path": QgsApplication.prefixPath(),
            "profile_path": safe_call(QgsApplication.qgisSettingsDirPath),
            "settings_path": safe_call(QgsApplication.qgisSettingsDirPath),
            "plugin_path": safe_call(QgsApplication.pluginPath),
            "default_project_crs": safe_call(lambda: QgsProject.instance().crs().authid()),
            "project_file": safe_call(lambda: QgsProject.instance().fileName()),
        }

        registry = QgsApplication.processingRegistry()
        providers = []
        algorithms_count = 0
        if registry:
            for provider in registry.providers():
                algs = list(provider.algorithms())
                algorithms_count += len(algs)
                providers.append(
                    {
                        "id": provider.id(),
                        "name": provider.name(),
                        "active": bool(provider.isActive()),
                        "algorithm_count": len(algs),
                    }
                )
        report["processing"] = {
            "available": True,
            "providers": providers,
            "algorithms_count": algorithms_count,
        }
    except Exception as exc:
        report["qgis"] = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
        report["processing"] = {"available": False}

    try:
        from osgeo import gdal, geos, osr  # type: ignore

        report["gdal"] = {"version": gdal.VersionInfo("--version")}
        report["geos"] = {"version": geos.VersionInfo()}
        report["proj"] = {"version": osr.GetPROJVersion()}
    except Exception as exc:
        report["gdal_geos_proj"] = {"error": f"{type(exc).__name__}: {exc}"}

    try:
        from qgis.PyQt.QtCore import QT_VERSION_STR, PYQT_VERSION_STR  # type: ignore

        report["qt"] = {"qt_version": QT_VERSION_STR, "pyqt_version": PYQT_VERSION_STR}
    except Exception as exc:
        report["qt"] = {"error": f"{type(exc).__name__}: {exc}"}

    try:
        import qgis.utils  # type: ignore

        report["plugins"] = {
            "active_plugins": sorted(list(getattr(qgis.utils, "active_plugins", []))),
            "loaded_plugins": sorted(list(getattr(qgis.utils, "plugins", {}).keys())),
        }
    except Exception as exc:
        report["plugins"] = {"error": f"{type(exc).__name__}: {exc}"}

    return report


def write_markdown(report: dict[str, Any]) -> None:
    qgis = report.get("qgis", {})
    processing = report.get("processing", {})
    lines = [
        "# QGIS Environment Report",
        "",
        f"Generated at: `{report.get('generated_at')}`",
        "",
        "## Python",
        "",
        f"- Executable: `{report['python']['executable']}`",
        f"- Version: `{report['python']['version']}`",
        "",
        "## QGIS",
        "",
        f"- Version: `{qgis.get('version', 'not detected')}`",
        f"- Version int: `{qgis.get('version_int', 'not detected')}`",
        f"- Prefix path: `{qgis.get('prefix_path', '')}`",
        f"- Profile/settings path: `{qgis.get('profile_path', '')}`",
        f"- Plugin path: `{qgis.get('plugin_path', '')}`",
        f"- Project file: `{qgis.get('project_file', '')}`",
        f"- Project CRS: `{qgis.get('default_project_crs', '')}`",
        "",
        "## Processing",
        "",
        f"- Available: `{processing.get('available', False)}`",
        f"- Algorithm count: `{processing.get('algorithms_count', 0)}`",
        "",
        "| Provider | Name | Active | Algorithms |",
        "|---|---|---:|---:|",
    ]
    for provider in processing.get("providers", []):
        lines.append(
            f"| `{provider.get('id')}` | {provider.get('name')} | {provider.get('active')} | {provider.get('algorithm_count')} |"
        )
    lines.extend(
        [
            "",
            "## Imports",
            "",
            "```json",
            json.dumps(report.get("imports", {}), indent=2, ensure_ascii=False),
            "```",
            "",
            "## Important Environment Variables",
            "",
            "```json",
            json.dumps(report.get("environment", {}), indent=2, ensure_ascii=False),
            "```",
        ]
    )
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    report = collect()
    JSON_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_markdown(report)
    print(str(JSON_REPORT))
    print(str(MD_REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
