from __future__ import annotations

from typing import Any

from .permissions import READ_ONLY, SCHEMA_VERSION, UNSAFE_DEVELOPER, allowed_actions, permission_for
from .security import contains_blocked_token


ALLOWED_ACTIONS = allowed_actions()

BLOCKED_TOKENS = {
    "__import__",
    "cmd",
    "code",
    "eval",
    "exec",
    "os.system",
    "popen",
    "python",
    "shell",
    "subprocess",
}


class ValidationError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def validate_command(command: Any, unsafe_developer_mode: bool = False) -> dict[str, Any]:
    if not isinstance(command, dict):
        raise ValidationError("BAD_REQUEST", "Command body must be a JSON object.")

    action = command.get("action")
    if not isinstance(action, str) or not action:
        raise ValidationError("BAD_REQUEST", "Command must include a non-empty action.")

    if action not in ALLOWED_ACTIONS:
        raise ValidationError("ACTION_NOT_ALLOWED", f"Action is not allowed: {action}", {"action": action})

    schema_version = command.get("schema_version", SCHEMA_VERSION)
    if not isinstance(schema_version, str) or not schema_version:
        raise ValidationError("BAD_REQUEST", "schema_version must be a non-empty string.", {"action": action})

    request_id = command.get("request_id", command.get("id", ""))
    if request_id is not None and not isinstance(request_id, str):
        raise ValidationError("BAD_REQUEST", "request_id must be a string when provided.", {"action": action})

    dry_run = command.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise ValidationError("BAD_REQUEST", "dry_run must be a boolean.", {"action": action})

    metadata = permission_for(action)
    if metadata and metadata.permission_level == UNSAFE_DEVELOPER and not unsafe_developer_mode:
        raise ValidationError(
            "DEV_MODE_REQUIRED",
            "This action requires SIGMAI DEV mode to be enabled from the QGIS UI.",
            {"action": action, "permission_level": metadata.permission_level},
        )
    if dry_run and metadata and not metadata.supports_dry_run and metadata.permission_level != READ_ONLY:
        raise ValidationError("DRY_RUN_NOT_SUPPORTED", "This action does not support dry_run.", {"action": action})

    params = command.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValidationError("BAD_REQUEST", "Command params must be a JSON object.", {"action": action})

    if metadata and metadata.requires_confirmation and not dry_run:
        confirmed = any(
            (
                params.get("confirm"),
                params.get("confirm_action"),
                params.get(f"confirm_{action}"),
                params.get("confirm_plugin_write"),
                str(params.get("confirm_dev_python", "")).strip().upper() == "SIM",
            )
        )
        if not confirmed:
            raise ValidationError(
                "CONFIRMATION_REQUIRED",
                "This action requires explicit confirmation. Run dry_run first, then pass a confirmation flag.",
                {"action": action, "permission_level": metadata.permission_level},
            )

    token_scan_payload = _redact_dev_code_values(command) if metadata and metadata.permission_level == UNSAFE_DEVELOPER and unsafe_developer_mode else command
    blocked = contains_blocked_token(_redact_path_values(token_scan_payload), BLOCKED_TOKENS)
    if blocked:
        raise ValidationError("DANGEROUS_COMMAND", "Command contains a blocked token.", {"token": blocked})

    normalized = dict(command)
    normalized["schema_version"] = schema_version
    normalized["request_id"] = request_id or ""
    normalized["dry_run"] = dry_run
    normalized["params"] = params
    return normalized


def _redact_path_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower == "action" and isinstance(nested, str) and nested in ALLOWED_ACTIONS:
                redacted[key] = "<allowed_action>"
            elif key_lower in {"request_id", "id"} and isinstance(nested, str):
                redacted[key] = "<request_id>"
            elif _is_path_like_key(key_lower) and isinstance(nested, str):
                redacted[key] = "<path>"
            else:
                redacted[key] = _redact_path_values(nested)
        return redacted
    if isinstance(value, list):
        return [_redact_path_values(item) for item in value]
    return value


def _redact_dev_code_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower in {"code", "script", "python_code"} and isinstance(nested, str):
                redacted["<dev_qgis_python_code>"] = "<redacted>"
            else:
                redacted[key] = _redact_dev_code_values(nested)
        return redacted
    if isinstance(value, list):
        return [_redact_dev_code_values(item) for item in value]
    return value


def _is_path_like_key(key_lower: str) -> bool:
    return any(
        (
            key_lower in {"path", "output", "input", "output_path", "source_folder", "backup_path"},
            key_lower.startswith("input_"),
            key_lower.startswith("output_"),
            key_lower.endswith("_path"),
            key_lower.endswith("_folder"),
            key_lower.endswith("_file"),
            key_lower.endswith("_raster"),
            key_lower.endswith("_vector"),
        )
    )


def require_param(params: dict[str, Any], name: str, expected_type: type) -> Any:
    value = params.get(name)
    if not isinstance(value, expected_type) or value == "":
        type_name = expected_type.__name__
        raise ValidationError("BAD_REQUEST", f"Missing or invalid parameter: {name}", {"expected_type": type_name})
    return value
