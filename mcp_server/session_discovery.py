from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION_DISCOVERY = ROOT / "tools" / "session_discovery.py"

spec = importlib.util.spec_from_file_location("sigmai_tools_session_discovery", SESSION_DISCOVERY)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load session discovery from {SESSION_DISCOVERY}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
resolve_connection = module.resolve_connection
