from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Iterable


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def generate_token() -> str:
    """Create a local session token for bearer authentication."""
    return secrets.token_urlsafe(32)


def is_localhost(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def validate_bearer_header(header_value: str | None, expected_token: str) -> bool:
    if not expected_token or not header_value:
        return False
    prefix = "Bearer "
    if not header_value.startswith(prefix):
        return False
    supplied = header_value[len(prefix):].strip()
    return secrets.compare_digest(supplied, expected_token)


def normalize_output_path(path_value: str) -> Path:
    """Normalize an output path without creating or deleting anything."""
    if not path_value or not isinstance(path_value, str):
        raise ValueError("Output path must be a non-empty string.")
    expanded = os.path.expandvars(os.path.expanduser(path_value))
    return Path(expanded).resolve()


def ensure_parent_exists(path: Path) -> None:
    if not path.parent.exists():
        raise ValueError(f"Output directory does not exist: {path.parent}")


def reject_existing_path_without_confirmation(path: Path, confirm_overwrite: bool) -> None:
    if path.exists() and not confirm_overwrite:
        raise FileExistsError(f"Output path already exists: {path}")


def contains_blocked_token(value: object, blocked: Iterable[str]) -> str | None:
    """Return the first blocked key/value token found in a nested JSON-like object."""
    blocked_lower = {item.lower() for item in blocked}
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower in blocked_lower:
                return str(key)
            found = contains_blocked_token(nested, blocked_lower)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = contains_blocked_token(nested, blocked_lower)
            if found:
                return found
    elif isinstance(value, str):
        lowered = value.lower()
        for token in blocked_lower:
            if _blocked_token_in_string(lowered, token):
                return token
    return None


def _blocked_token_in_string(lowered: str, token: str) -> bool:
    if token in {"cmd", "code", "eval", "exec", "os.system", "popen", "python", "shell", "subprocess"}:
        pattern = rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])"
        return re.search(pattern, lowered) is not None
    return token in lowered
