from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..permissions import permission_for
from ..security import normalize_output_path, reject_existing_path_without_confirmation
from ..validators import ValidationError, require_param


def _workflow_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or str(Path.home())
    path = Path(base) / "SIGMAI" / "workflows"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_steps(steps: Any, registered_actions: list[str]) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        raise ValidationError("BAD_REQUEST", "workflow steps must be a non-empty list.", {"steps_type": type(steps).__name__})
    allowed = set(registered_actions)
    normalized = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValidationError("BAD_REQUEST", "workflow step must be an object.", {"index": index})
        action = step.get("action")
        if not isinstance(action, str) or not action:
            raise ValidationError("BAD_REQUEST", "workflow step action is required.", {"index": index})
        if action not in allowed:
            raise ValidationError("ACTION_NOT_ALLOWED", "workflow step action is not registered.", {"index": index, "action": action})
        permission = permission_for(action)
        if permission and permission.permission_level in {"dangerous_plugin_write", "unsafe_developer"}:
            raise ValidationError("WORKFLOW_UNSAFE_ACTION", "Dangerous actions are not allowed inside workflows.", {"index": index, "action": action})
        normalized.append(
            {
                "index": index,
                "action": action,
                "params": step.get("params", {}),
                "dry_run": bool(step.get("dry_run", True)),
                "permission_level": permission.permission_level if permission else "unknown",
                "requires_confirmation": bool(permission.requires_confirmation) if permission else False,
            }
        )
    return normalized


def plan_workflow(params: dict[str, Any], context: dict[str, Any]):
    steps = _validate_steps(require_param(params, "steps", list), context.get("registered_actions", []))
    outputs = []
    warnings = []
    for step in steps:
        if step["requires_confirmation"]:
            warnings.append(f"Step {step['index']} action '{step['action']}' requires confirmation outside the workflow.")
        outputs.append({"step": step["index"], "action": step["action"], "mode": "dry_run" if step["dry_run"] else "real"})
    return {
        "workflow_name": params.get("name", "SIGMAI workflow"),
        "step_count": len(steps),
        "steps": steps,
        "planned_outputs": outputs,
        "warnings": warnings,
        "execution_policy": "planning_only_until_job_runner_is_enabled",
    }


def dry_run_workflow(params: dict[str, Any], context: dict[str, Any]):
    plan = plan_workflow(params, context)
    plan["dry_run"] = True
    plan["changes"] = ["Validate workflow structure and report the planned command sequence without executing QGIS mutations."]
    return plan


def execute_workflow(params: dict[str, Any], context: dict[str, Any]):
    plan = plan_workflow(params, context)
    if context.get("dry_run"):
        plan["dry_run"] = True
        return plan
    raise ValidationError(
        "WORKFLOW_EXECUTION_NOT_ENABLED",
        "Workflow execution is intentionally disabled until the SIGMAI job runner is available. Use dry_run_workflow or execute individual steps.",
        {"step_count": plan["step_count"]},
    )


def save_workflow_template(params: dict[str, Any], context: dict[str, Any]):
    name = require_param(params, "name", str)
    steps = _validate_steps(require_param(params, "steps", list), context.get("registered_actions", []))
    output_path = normalize_output_path(params.get("output_path") or str(_workflow_dir() / f"{name}.json"))
    if output_path.suffix.lower() != ".json":
        raise ValidationError("BAD_REQUEST", "Workflow template output must be a .json file.", {"output_path": str(output_path)})
    try:
        reject_existing_path_without_confirmation(output_path, bool(params.get("confirm_overwrite")))
    except FileExistsError as exc:
        raise ValidationError("OVERWRITE_BLOCKED", str(exc), {"path": str(output_path)}) from exc
    if not output_path.parent.exists():
        raise ValidationError("BAD_REQUEST", "Output directory does not exist.", {"path": str(output_path.parent)})
    payload = {
        "name": name,
        "description": params.get("description", ""),
        "steps": steps,
        "safety": {
            "no_arbitrary_python": True,
            "dangerous_actions_blocked": True,
            "prefer_dry_run": True,
        },
    }
    if context.get("dry_run"):
        return {"dry_run": True, "output_path": str(output_path), "template": payload}
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"output_path": str(output_path), "step_count": len(steps)}


def list_workflow_templates(params: dict[str, Any], context: dict[str, Any]):
    directory = _workflow_dir()
    templates = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        templates.append({"name": data.get("name", path.stem), "path": str(path), "step_count": len(data.get("steps", [])) if isinstance(data.get("steps"), list) else 0})
    return {"template_dir": str(directory), "templates": templates}


def run_workflow_template(params: dict[str, Any], context: dict[str, Any]):
    path = normalize_output_path(require_param(params, "path", str))
    if not path.exists() or not path.is_file():
        raise ValidationError("FILE_NOT_FOUND", "Workflow template was not found.", {"path": str(path)})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("BAD_REQUEST", "Workflow template is not valid JSON.", {"path": str(path)}) from exc
    merged = dict(data)
    merged["steps"] = data.get("steps", [])
    return execute_workflow(merged, {**context, "dry_run": bool(params.get("dry_run", True) or context.get("dry_run"))})
