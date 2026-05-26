from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path


def _init_qgis() -> object:
    from qgis.core import QgsApplication  # type: ignore

    prefix = os.environ.get("QGIS_PREFIX_PATH", r"C:/PROGRA~1/QGIS34~1.7/apps/qgis-ltr")
    QgsApplication.setPrefixPath(prefix, True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        import processing  # noqa: F401  # type: ignore
        from processing.core.Processing import Processing  # type: ignore

        Processing.initialize()
    except Exception:
        pass
    return app


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[1] / "qgis_plugin"
    sys.path.insert(0, str(plugin_root.parent))
    app = _init_qgis()

    from qgis_plugin.bridge_server import SIGMAIServer
    from qgis_plugin.security import DEFAULT_HOST, DEFAULT_PORT, generate_token

    token = os.environ.get("SIGMAI_TOKEN") or generate_token()
    server = SIGMAIServer(iface=None, host=DEFAULT_HOST, port=DEFAULT_PORT, token=token, log_dir=plugin_root / "logs")
    server._start_qt_timer = lambda: None  # type: ignore[method-assign]
    server.start()
    ready_path = Path(os.environ.get("SIGMAI_HEADLESS_READY", plugin_root.parent / "test_outputs" / "sigmai_headless_bridge_ready.txt"))
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.write_text(f"SIGMAI headless bridge online at {DEFAULT_HOST}:{DEFAULT_PORT}\n", encoding="utf-8")
    print(f"SIGMAI headless bridge online at {DEFAULT_HOST}:{DEFAULT_PORT}")

    stop = False

    def _stop(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        while not stop:
            time.sleep(0.5)
    finally:
        server.stop()
        try:
            app.exitQgis()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
