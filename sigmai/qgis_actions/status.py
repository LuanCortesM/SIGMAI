from __future__ import annotations

from .common import project, qgis_imports


def handle(params, context):
    imports = qgis_imports()
    qgis_version = imports["Qgis"].QGIS_VERSION
    qgs_project = project()
    return {
        "display_name": "SIGMAI",
        "subtitle": "Secure GIS-AI Interface",
        "bridge": "online",
        "host": context.get("host"),
        "port": context.get("port"),
        "qgis_version": qgis_version,
        "project_loaded": bool(qgs_project.fileName()),
        "unsafe_developer_mode": bool(context.get("unsafe_developer_mode", False)),
    }


def bridge_config(params, context):
    return {
        "host": context.get("host"),
        "port": context.get("port"),
        "token_required": True,
        "transport": "http_localhost",
        "endpoints": {
            "command": "/command",
            "status": "/status",
        },
        "unsafe_developer_mode": bool(context.get("unsafe_developer_mode", False)),
        "display_name": "SIGMAI",
        "subtitle": "Secure GIS-AI Interface",
        "local_only": True,
    }
