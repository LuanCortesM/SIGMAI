from __future__ import annotations

import os
import random
import string
from pathlib import Path

SESSION_SCHEMA_VERSION = "0.3"
APP_NAME = "SIGMAI"
SESSION_FILE = "current_bridge_session.json"


def sessions_dir() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / APP_NAME / "sessions"
        temp = os.environ.get("TEMP")
        if temp:
            return Path(temp) / APP_NAME / "sessions"
    if os.name == "posix":
        if "darwin" in os.sys.platform:
            return Path.home() / "Library" / "Application Support" / APP_NAME / "sessions"
        return Path.home() / ".local" / "share" / "sigmai" / "sessions"
    return Path(os.environ.get("TEMP", str(Path.home()))) / APP_NAME / "sessions"


def fallback_sessions_dir() -> Path:
    return Path(os.environ.get("TEMP", str(Path.home()))) / APP_NAME / "sessions"


def legacy_sessions_dirs() -> list[Path]:
    return []


def current_session_file() -> Path:
    return sessions_dir() / SESSION_FILE


def pairing_session_file(pairing_code: str) -> Path:
    return sessions_dir() / f"{pairing_code.upper()}.json"


def is_safe_session_path(path: Path) -> bool:
    return ".git" not in {part.lower() for part in path.resolve().parts}


def generate_pairing_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    part1 = "".join(random.choice(string.digits) for _ in range(4))
    part2 = "".join(random.choice(alphabet) for _ in range(4))
    return f"SG-{part1}-{part2}"
