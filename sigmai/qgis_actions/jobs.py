from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ..permissions import READ_ONLY, permission_for
from ..validators import ValidationError, require_param


_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _public_job(job: dict[str, Any], include_result: bool = False, include_logs: bool = False) -> dict[str, Any]:
    payload = {key: job.get(key) for key in ["job_id", "name", "action", "status", "progress", "created_at", "started_at", "finished_at", "dry_run", "warnings", "errors"]}
    if include_result:
        payload["result"] = job.get("result")
    if include_logs:
        payload["logs"] = job.get("logs", [])
    return payload


def _get_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise ValidationError("JOB_NOT_FOUND", "Job was not found.", {"job_id": job_id})
        return job


def _validate_job_action(action: str, dry_run: bool, context: dict[str, Any]) -> None:
    registered = set(context.get("registered_actions", []))
    if action not in registered:
        raise ValidationError("ACTION_NOT_ALLOWED", "Job action is not registered.", {"action": action})
    if action in {"start_job", "run_processing_job", "run_workflow_job", "run_raster_job", "run_map_export_job"}:
        raise ValidationError("JOB_RECURSION_BLOCKED", "Job commands cannot start nested jobs.", {"action": action})
    permission = permission_for(action)
    if permission and permission.permission_level != READ_ONLY and not dry_run:
        raise ValidationError(
            "JOB_UNSAFE_ACTION_USE_DRY_RUN",
            "Background jobs currently allow read-only actions or dry-run mutations only. Real QGIS mutations require the future QgsTask runner.",
            {"action": action, "permission_level": permission.permission_level},
        )


def _run_job(job_id: str, command: dict[str, Any], executor: Any) -> None:
    with _LOCK:
        job = _JOBS[job_id]
        if job["status"] == "cancelled":
            job["finished_at"] = _now()
            return
        job["status"] = "running"
        job["started_at"] = _now()
        job["progress"] = 10
        job["logs"].append({"timestamp": _now(), "message": "Job started."})
    try:
        if executor is None:
            raise ValidationError("JOB_EXECUTOR_UNAVAILABLE", "Command executor is not available in this runtime.")
        with _LOCK:
            _JOBS[job_id]["progress"] = 40
        result = executor(command)
        with _LOCK:
            job = _JOBS[job_id]
            job["result"] = result
            job["status"] = "completed" if result.get("ok") else "failed"
            job["progress"] = 100
            job["finished_at"] = _now()
            job["warnings"] = result.get("warnings", [])
            job["errors"] = result.get("errors", [])
            job["logs"].append({"timestamp": _now(), "message": f"Job finished with status {job['status']}."})
    except ValidationError as exc:
        with _LOCK:
            job = _JOBS[job_id]
            job["status"] = "failed"
            job["progress"] = 100
            job["finished_at"] = _now()
            job["errors"] = [{"code": exc.code, "message": str(exc), "details": exc.details}]
            job["logs"].append({"timestamp": _now(), "message": f"Job failed: {exc.code}."})
    except Exception as exc:
        with _LOCK:
            job = _JOBS[job_id]
            job["status"] = "failed"
            job["progress"] = 100
            job["finished_at"] = _now()
            job["errors"] = [{"code": "JOB_INTERNAL_ERROR", "message": str(exc), "details": {"type": type(exc).__name__}}]
            job["logs"].append({"timestamp": _now(), "message": "Job failed with internal error."})


def start_job(params: dict[str, Any], context: dict[str, Any]):
    action = require_param(params, "action", str)
    dry_run = bool(params.get("dry_run", True))
    command_params = params.get("params", {})
    if not isinstance(command_params, dict):
        raise ValidationError("BAD_REQUEST", "params.params must be an object.", {"action": action})
    _validate_job_action(action, dry_run, context)
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "name": params.get("name") or f"SIGMAI job {action}",
        "action": action,
        "params": command_params,
        "dry_run": dry_run,
        "status": "queued",
        "progress": 0,
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "warnings": [],
        "errors": [],
        "logs": [{"timestamp": _now(), "message": "Job queued."}],
    }
    with _LOCK:
        _JOBS[job_id] = job
    command = {
        "schema_version": "0.3",
        "request_id": f"job-{job_id}",
        "action": action,
        "params": command_params,
        "dry_run": dry_run,
    }
    thread = threading.Thread(target=_run_job, args=(job_id, command, context.get("command_executor")), name=f"SIGMAIJob-{job_id[:8]}", daemon=True)
    thread.start()
    return _public_job(job)


def get_job_status(params: dict[str, Any], context: dict[str, Any]):
    return _public_job(_get_job(require_param(params, "job_id", str)))


def get_job_result(params: dict[str, Any], context: dict[str, Any]):
    return _public_job(_get_job(require_param(params, "job_id", str)), include_result=True)


def list_jobs(params: dict[str, Any], context: dict[str, Any]):
    limit = int(params.get("limit", 50))
    with _LOCK:
        jobs = list(_JOBS.values())[-limit:]
        return {"jobs": [_public_job(job) for job in jobs], "count": len(jobs), "total": len(_JOBS)}


def cancel_job(params: dict[str, Any], context: dict[str, Any]):
    job = _get_job(require_param(params, "job_id", str))
    with _LOCK:
        if job["status"] == "queued":
            job["status"] = "cancelled"
            job["progress"] = 100
            job["finished_at"] = _now()
            job["logs"].append({"timestamp": _now(), "message": "Job cancelled before execution."})
            return _public_job(job)
        return {**_public_job(job), "cancelled": False, "warning": "Only queued jobs can be cancelled by the initial SIGMAI job runner."}


def job_logs(params: dict[str, Any], context: dict[str, Any]):
    return _public_job(_get_job(require_param(params, "job_id", str)), include_logs=True)


def clear_finished_jobs(params: dict[str, Any], context: dict[str, Any]):
    with _LOCK:
        removable = [job_id for job_id, job in _JOBS.items() if job.get("status") in {"completed", "failed", "cancelled"}]
        for job_id in removable:
            _JOBS.pop(job_id, None)
    return {"cleared": len(removable), "remaining": len(_JOBS)}


def run_processing_job(params: dict[str, Any], context: dict[str, Any]):
    return start_job({"action": "run_processing", "params": params, "dry_run": bool(params.get("dry_run", True)), "name": "SIGMAI Processing dry-run job"}, context)


def run_workflow_job(params: dict[str, Any], context: dict[str, Any]):
    return start_job({"action": "dry_run_workflow", "params": params, "dry_run": False, "name": "SIGMAI workflow dry-run job"}, context)


def run_raster_job(params: dict[str, Any], context: dict[str, Any]):
    action = str(params.get("raster_action", "raster_info"))
    command_params = dict(params)
    command_params.pop("raster_action", None)
    return start_job({"action": action, "params": command_params, "dry_run": bool(params.get("dry_run", True)), "name": f"SIGMAI raster job {action}"}, context)


def run_map_export_job(params: dict[str, Any], context: dict[str, Any]):
    action = str(params.get("map_action", "generate_professional_map"))
    command_params = dict(params)
    command_params.pop("map_action", None)
    return start_job({"action": action, "params": command_params, "dry_run": True, "name": f"SIGMAI map export dry-run job {action}"}, context)
