from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any

from .common import crs_authid, project, qgis_imports


def _safe_profile_folder() -> str:
    try:
        imports = qgis_imports()
        return imports["QgsApplication"].qgisSettingsDirPath()
    except Exception:
        return ""


def _safe_plugin_paths() -> list[str]:
    try:
        imports = qgis_imports()
        return [str(path) for path in imports["QgsApplication"].pluginPath().split(os.pathsep) if path]
    except Exception:
        return []


def _processing_providers() -> list[dict[str, Any]]:
    try:
        imports = qgis_imports()
        registry = imports["QgsApplication"].processingRegistry()
        return [
            {"id": provider.id(), "name": provider.name(), "active": bool(provider.isActive())}
            for provider in registry.providers()
        ]
    except Exception:
        return []


def _installed_plugins() -> list[dict[str, Any]]:
    plugins = []
    try:
        import qgis.utils  # type: ignore

        active = set(getattr(qgis.utils, "active_plugins", []))
        loaded = getattr(qgis.utils, "plugins", {})
        for name in sorted(set(active) | set(loaded.keys())):
            plugins.append({"name": name, "active": name in active, "loaded": name in loaded})
    except Exception:
        pass
    return plugins


def handle(params: dict[str, Any], context: dict[str, Any]):
    qgs_project = project()
    profile_folder = _safe_profile_folder()
    plugin_paths = _safe_plugin_paths()
    return {
        "qgis_version": context.get("qgis_version") or qgis_imports()["Qgis"].QGIS_VERSION,
        "python_version": sys.version,
        "platform": platform.platform(),
        "profile_folder": profile_folder,
        "plugin_paths": plugin_paths,
        "primary_plugin_path": plugin_paths[0] if plugin_paths else "",
        "project_path": qgs_project.fileName(),
        "project_folder": str(Path(qgs_project.fileName()).parent) if qgs_project.fileName() else "",
        "project_crs": crs_authid(qgs_project.crs()),
        "processing_providers": _processing_providers(),
        "installed_plugins": _installed_plugins(),
    }
