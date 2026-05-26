from __future__ import annotations

from qgis.PyQt.QtCore import QTimer


def _start_sigmai() -> None:
    try:
        import qgis.utils

        if "sigmai" not in qgis.utils.plugins:
            qgis.utils.loadPlugin("sigmai")
            qgis.utils.startPlugin("sigmai")
        plugin = qgis.utils.plugins.get("sigmai")
        if plugin and hasattr(plugin, "start_bridge"):
            plugin.start_bridge()
            print("SIGMAI bridge start requested.")
        else:
            print("SIGMAI plugin is not loaded or has no start_bridge method.")
    except Exception as exc:
        print(f"Could not start SIGMAI bridge: {type(exc).__name__}: {exc}")


QTimer.singleShot(3000, _start_sigmai)
