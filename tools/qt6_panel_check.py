#!/usr/bin/env python3
"""Constrói o painel do SIGMAI contra o PyQt6, sem precisar do QGIS 4.

O QGIS expõe o binding em uso através do módulo ``qgis.PyQt``. Aqui esse módulo
é fabricado apontando para o PyQt6 real, o que reproduz exatamente o ambiente
do QGIS 4 para todo o código de interface — que é onde os enums do Qt são
tocados. Se o painel constrói e responde aqui, ele abre lá.
"""

from __future__ import annotations

import datetime
import os
import sys
import traceback
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install_qgis_pyqt_shim() -> None:
    """Cria um pacote 'qgis.PyQt' que reexporta o PyQt6, como o QGIS 4 faz."""
    import PyQt6

    qgis = types.ModuleType("qgis")
    qgis.__path__ = []  # type: ignore[attr-defined]
    pyqt = types.ModuleType("qgis.PyQt")
    pyqt.__path__ = []  # type: ignore[attr-defined]
    sys.modules["qgis"] = qgis
    sys.modules["qgis.PyQt"] = pyqt
    qgis.PyQt = pyqt  # type: ignore[attr-defined]

    for name in ("QtCore", "QtGui", "QtWidgets", "QtSvg", "QtNetwork", "QtXml", "QtPrintSupport"):
        try:
            source = __import__(f"PyQt6.{name}", fromlist=[name])
        except ImportError:
            continue
        module = types.ModuleType(f"qgis.PyQt.{name}")
        module.__dict__.update(source.__dict__)
        sys.modules[f"qgis.PyQt.{name}"] = module
        setattr(pyqt, name, module)


class FakeServer:
    running = True
    host = "127.0.0.1"
    port = 8765
    qgis_version = "4.1.0"
    unsafe_developer_mode = False


class FakeController:
    """Controlador mínimo: o painel só conhece este protocolo."""

    def __init__(self):
        from sigmai.consent import ConsentManager, ConsentRequest

        self.server = FakeServer()
        self.consent = ConsentManager(mode="ask")
        self.consent.set_output_roots(["C:/SIG/saidas"])
        self.consent._record(
            "allowed",
            request=ConsentRequest("compose_map", "cartography", "safe_write", {"output_path": "C:/x.pdf"}, "127.0.0.1").to_dict(),
        )
        self.token = "k" * 44
        self.session_id = "SG-0000-TEST"
        self.language = "pt-BR"

    def start_bridge(self): self.server.running = True
    def stop_bridge(self): self.server.running = False
    def set_language(self, language): self.language = language
    def session_file_path(self): return Path("/tmp/sessao.json")
    def settings_get(self, key, default=None): return True
    def settings_set(self, key, value): pass
    def copy_to_clipboard(self, text): pass
    def open_path(self, path): pass
    def open_diagnostics(self): pass
    def regenerate_token(self): pass
    def toggle_dev_mode(self): pass
    def plugin_version(self): return "0.2.0"
    def utc_now(self): return datetime.datetime.now(datetime.timezone.utc).isoformat()
    def run_self_test(self): return [{"ok": True, "label": "Ponte local", "detail": "ok"}]


def main() -> int:
    try:
        install_qgis_pyqt_shim()
    except ImportError:
        print("PyQt6 não instalado; verificação ignorada.")
        return 0

    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import QApplication

    from sigmai.ui.panel import SigmaiPanel
    from sigmai.ui.theme import get_sigmai_stylesheet

    failures: list[str] = []

    def step(label, action):
        try:
            action()
            print(f"  OK    {label}")
        except Exception:
            print(f"  FALHA {label}")
            print("        " + traceback.format_exc().strip().splitlines()[-1])
            failures.append(label)

    app = QApplication([])
    controller = FakeController()
    panel = SigmaiPanel(controller)

    step("folha de estilo", lambda: panel.setStyleSheet(get_sigmai_stylesheet(1.0)))
    step("refresh", panel.refresh)
    step("trocar idioma", panel._toggle_language)
    step("percorrer clientes de IA", lambda: [
        (panel.client_combo.setCurrentIndex(index), app.processEvents())
        for index in range(panel.client_combo.count())
    ])
    step("autoteste", panel._run_self_test)
    step("modos de acesso", lambda: [panel.mode_buttons[mode].setChecked(True) for mode in ("read_only", "ask", "allow_session")])
    step("mostrar/ocultar token", lambda: (panel._toggle_token_visibility(), panel._toggle_token_visibility()))
    step("trilha de atividade", panel.refresh_activity)
    step("desenhar", lambda: (panel.resize(QSize(780, 940)), panel.show(), app.processEvents(), panel.grab()))

    print(f"\n{len(failures)} falha(s) sob Qt6")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
