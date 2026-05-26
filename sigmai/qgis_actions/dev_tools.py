from __future__ import annotations

import contextlib
import io
from typing import Any

from ..validators import ValidationError, require_param


BLOCKED_DEV_TOKENS = {
    "subprocess",
    "os.system",
    "popen",
    "startfile",
    "shutil.rmtree",
    "socket",
    "requests.",
    "urllib.request",
}


def dev_mode_status(params: dict[str, Any], context: dict[str, Any]):
    return {
        "enabled": bool(context.get("unsafe_developer_mode", False)),
        "risk_level": "critical",
        "confirmation_phrase": "SIM",
        "python_execution_command": "dev_execute_qgis_python",
        "warning": "DEV mode can corrupt the current QGIS session or project. Use only for plugin development and controlled tests.",
    }


def execute_qgis_python(params: dict[str, Any], context: dict[str, Any]):
    if not bool(context.get("unsafe_developer_mode", False)):
        raise ValidationError(
            "DEV_MODE_REQUIRED",
            "QGIS Python execution is available only when SIGMAI DEV mode is enabled from the QGIS UI.",
            {"action": "dev_execute_qgis_python"},
        )
    code = require_param(params, "code", str)
    if not code.strip():
        raise ValidationError("BAD_REQUEST", "code must not be empty.", {})
    if context.get("dry_run"):
        return {
            "dry_run": True,
            "would_execute": "QGIS Python code in the active QGIS process.",
            "code_preview": code[:500],
            "warnings": [
                "DEV mode code can mutate the QGIS project, plugin state and in-memory layers.",
                "Original files are not protected unless the code protects them.",
            ],
        }
    if str(params.get("confirm_dev_python", "")).strip().upper() != "SIM":
        raise ValidationError(
            "DEV_CONFIRMATION_REQUIRED",
            "Type SIM in confirm_dev_python to execute QGIS Python in DEV mode.",
            {"required": "SIM"},
        )
    blocked = _blocked_dev_token(code)
    if blocked:
        raise ValidationError(
            "DEV_TOKEN_BLOCKED",
            "This DEV command is for QGIS/PyQGIS automation, not OS shell or network execution.",
            {"token": blocked},
        )
    namespace = _dev_namespace(context)
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            compiled = compile(code, "<SIGMAI_DEV_QGIS_PYTHON>", "exec")
            exec(compiled, namespace, namespace)  # nosec B102 - gated DEV mode only, disabled by default and requires UI opt-in plus confirm_dev_python=SIM.
    except Exception as exc:
        raise ValidationError(
            "DEV_PYTHON_ERROR",
            "QGIS Python code raised an exception.",
            {"type": type(exc).__name__, "message": str(exc), "stdout": stdout.getvalue()[-4000:]},
        ) from exc
    result = namespace.get("result", None)
    return {
        "executed": True,
        "stdout": stdout.getvalue()[-4000:],
        "result_repr": repr(result)[:4000],
        "result_type": type(result).__name__ if result is not None else "NoneType",
        "warnings": [
            "Executed inside QGIS DEV mode.",
            "Review QGIS project state before saving.",
        ],
    }


def _blocked_dev_token(code: str) -> str:
    lowered = code.lower()
    for token in sorted(BLOCKED_DEV_TOKENS):
        if token.lower() in lowered:
            return token
    return ""


def _dev_namespace(context: dict[str, Any]) -> dict[str, Any]:
    namespace: dict[str, Any] = {
        "__name__": "__sigmai_dev__",
        "iface": context.get("iface"),
        "result": None,
    }
    try:
        from qgis.core import QgsApplication, QgsProject, QgsVectorLayer, QgsRasterLayer, QgsCoordinateReferenceSystem  # type: ignore

        namespace.update(
            {
                "QgsApplication": QgsApplication,
                "QgsProject": QgsProject,
                "QgsVectorLayer": QgsVectorLayer,
                "QgsRasterLayer": QgsRasterLayer,
                "QgsCoordinateReferenceSystem": QgsCoordinateReferenceSystem,
                "project": QgsProject.instance(),
            }
        )
    except Exception:
        pass
    return namespace
