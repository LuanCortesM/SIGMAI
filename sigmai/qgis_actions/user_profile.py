from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_USER_PROFILE = {
    "default_map_author": "",
    "default_map_author_email": "",
    "default_organization": "",
    "default_credit_line": "",
    "use_plugin_author_as_map_author_in_dev": True,
}


def _profile_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or str(Path.home())
    path = Path(base) / "SIGMAI" / "settings"
    return path / "user_profile.json"


def read_user_profile() -> dict[str, Any]:
    path = _profile_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return dict(DEFAULT_USER_PROFILE)
    if not path.exists():
        return dict(DEFAULT_USER_PROFILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    profile = dict(DEFAULT_USER_PROFILE)
    for key in DEFAULT_USER_PROFILE:
        if key in data:
            profile[key] = data[key]
    return profile


def get_user_profile(params: dict[str, Any], context: dict[str, Any]):
    return {"path": str(_profile_path()), "profile": read_user_profile()}


def set_user_profile(params: dict[str, Any], context: dict[str, Any]):
    profile = read_user_profile()
    for key in DEFAULT_USER_PROFILE:
        if key in params:
            value = params[key]
            if key == "use_plugin_author_as_map_author_in_dev":
                profile[key] = bool(value)
            else:
                profile[key] = str(value)
    if context.get("dry_run"):
        return {"dry_run": True, "would_write": str(_profile_path()), "profile": profile}
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"path": str(path), "profile": profile}


def clear_user_profile(params: dict[str, Any], context: dict[str, Any]):
    profile = dict(DEFAULT_USER_PROFILE)
    if context.get("dry_run"):
        return {"dry_run": True, "would_write": str(_profile_path()), "profile": profile}
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"path": str(path), "profile": profile}
