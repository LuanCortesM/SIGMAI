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


#: Ações de orquestração de workflow: um passo apontando de volta para uma
#: destas recriaria a própria pilha de execução (execute_workflow chamando
#: execute_workflow chamando...) sem nunca terminar. jobs.py já bloqueia a
#: recursão equivalente para start_job/run_*_job; este é o mesmo bloqueio
#: para workflows, agora que execute_workflow de fato executa passo a passo.
WORKFLOW_RECURSION_BLOCKED = frozenset({"execute_workflow", "run_workflow_template"})


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
        if action in WORKFLOW_RECURSION_BLOCKED:
            raise ValidationError("WORKFLOW_UNSAFE_ACTION", "A workflow step cannot itself trigger workflow execution.", {"index": index, "action": action})
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
        "step_outputs": outputs,
        "warnings": warnings,
        "execution_policy": "dry_run_preview_or_step_by_step_execution",
    }


def dry_run_workflow(params: dict[str, Any], context: dict[str, Any]):
    plan = plan_workflow(params, context)
    plan["dry_run"] = True
    plan["changes"] = ["Validate workflow structure and report the step sequence without executing QGIS mutations."]
    return plan


def execute_workflow(params: dict[str, Any], context: dict[str, Any]):
    """Executa um workflow passo a passo pelo mesmo caminho validado da ponte.

    Cada passo vira um comando completo despachado por
    ``context["command_executor"]`` (o ``CommandRegistry.execute`` da própria
    ponte) — o mesmo ``validate_command`` que qualquer chamada direta atra-
    vessa, então consentimento, confirmação e ``dry_run`` por passo valem
    exatamente como valeriam se o passo tivesse sido pedido sozinho. Para no
    primeiro passo que falhar e devolve o que já executou e o que ainda falta,
    em vez de abortar o workflow inteiro sem dizer onde parou.
    """
    plan = plan_workflow(params, context)
    if context.get("dry_run"):
        plan["dry_run"] = True
        return plan
    executor = context.get("command_executor")
    if executor is None:
        raise ValidationError(
            "WORKFLOW_EXECUTOR_UNAVAILABLE",
            "Workflow execution requires the bridge's command dispatcher (context['command_executor']), "
            "which this call context does not provide.",
            {"step_count": plan["step_count"]},
        )
    executed_steps: list[dict[str, Any]] = []
    for step in plan["steps"]:
        command = {
            "schema_version": "0.3",
            "action": step["action"],
            "params": step["params"],
            "dry_run": step["dry_run"],
        }
        response = executor(command)
        entry = {
            "step": step["index"],
            "action": step["action"],
            "dry_run": step["dry_run"],
            "ok": bool(response.get("ok")),
        }
        if response.get("ok"):
            entry["result"] = response.get("data")
            executed_steps.append(entry)
            continue
        entry["errors"] = response.get("errors", [])
        executed_steps.append(entry)
        pending_steps = [
            {"step": pending["index"], "action": pending["action"]}
            for pending in plan["steps"]
            if pending["index"] > step["index"]
        ]
        return {
            "workflow_name": plan["workflow_name"],
            "step_count": plan["step_count"],
            "executed_steps": executed_steps,
            "pending_steps": pending_steps,
            "stopped_at_step": step["index"],
            "ok": False,
            "dry_run": False,
        }
    return {
        "workflow_name": plan["workflow_name"],
        "step_count": plan["step_count"],
        "executed_steps": executed_steps,
        "pending_steps": [],
        "ok": True,
        "dry_run": False,
    }


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
