from __future__ import annotations

"""Run inside the QGIS Python Console to start SIGMAI without clicking."""

import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    import qgis.utils  # type: ignore

    plugin = qgis.utils.plugins.get("sigmai")
    if plugin is None:
        raise RuntimeError("SIGMAI plugin is not loaded. Enable it in QGIS Plugin Manager first.")
    plugin.start_bridge()
    session_path = Path(plugin.__class__.__module__.split(".")[0])
    payload = {
        "host": "127.0.0.1",
        "port": 8765,
        "token": plugin.token,
        "running": plugin.server.running,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "qgis_bootstrap",
        "note": "The plugin also writes its own diagnostics/current_bridge_session.json file.",
    }
    print(json.dumps(payload, indent=2))


main()
