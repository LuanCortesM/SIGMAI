"""Ponto de entrada do plugin SIGMAI no QGIS.

Esta classe faz três coisas: registra a ação no menu e na barra de ferramentas,
mantém a ponte local viva, e serve de *controlador* para o painel — o painel
não conhece o QGIS, só este objeto. A separação existe para que a interface
possa ser renderizada e testada com um controlador falso, fora de uma sessão
interativa do QGIS.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge_server import SIGMAIServer
from .consent import DECISION_ALLOWED, DECISION_DENIED, MODE_READ_ONLY, MODES
from .security import DEFAULT_HOST, DEFAULT_PORT, generate_token
from .session import (
    build_session_payload,
    cleanup_old_sessions,
    generate_pairing_code,
    invalidate_session_file,
    session_file_path,
    sessions_dir,
    write_session_file,
)

SETTINGS_PREFIX = "SIGMAI"
SETTINGS_DEFAULTS: dict[str, Any] = {
    "auto_start": True,
    "write_session_file": True,
    "persist_token": True,
    "consent_mode": MODE_READ_ONLY,
    "ui_language": "pt-BR",
    "output_roots": "",
    "limit_writes_per_session": 200,
    "limit_exports_per_session": 60,
    "limit_processing_runs_per_session": 120,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SIGMAIPlugin:
    def __init__(self, iface: Any):
        self.iface = iface
        self.action = None
        self.dock = None
        self.panel = None
        self.last_error = ""
        self.session_file = None
        self.session_id = generate_pairing_code()
        self.token = self._load_or_create_token()
        self.language = str(self.settings_get("ui_language", "pt-BR"))
        self.server = SIGMAIServer(
            iface=iface,
            host=DEFAULT_HOST,
            port=DEFAULT_PORT,
            token=self.token,
            log_dir=Path(__file__).resolve().parent / "logs",
        )
        self.consent = self.server.consent
        self._restore_consent_settings()
        self.consent.set_prompt(self._prompt_for_consent)

    # -- ciclo de vida do plugin -----------------------------------------
    def initGui(self) -> None:
        try:
            from qgis.PyQt.QtCore import QTimer  # type: ignore
            from qgis.PyQt.QtGui import QIcon  # type: ignore
        except Exception:
            return
        try:  # Qt6 moveu QAction para QtGui
            from qgis.PyQt.QtGui import QAction  # type: ignore
        except Exception:
            from qgis.PyQt.QtWidgets import QAction  # type: ignore

        icon = QIcon(str(Path(__file__).resolve().parent / "icons" / "sigmai_icon.png"))
        self.action = QAction(icon, "SIGMAI", self.iface.mainWindow())
        self.action.setToolTip("SIGMAI — ponte segura entre assistentes de IA e o QGIS")
        self.action.triggered.connect(self.show_panel)
        self.iface.addPluginToMenu("&SIGMAI", self.action)
        self.iface.addToolBarIcon(self.action)
        if bool(self.settings_get("auto_start", True)):
            QTimer.singleShot(1500, self.start_bridge)

    def unload(self) -> None:
        self.stop_bridge(quiet=True)
        if self.dock is not None:
            try:
                self.iface.removeDockWidget(self.dock)
                self.dock.deleteLater()
            except Exception:
                pass
            self.dock = None
            self.panel = None
        if self.action is not None:
            self.iface.removePluginMenu("&SIGMAI", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def show_panel(self) -> None:
        if self.dock is None:
            self._create_dock()
        if self.panel is not None:
            self.panel.refresh()
        self.dock.show()
        self.dock.raise_()

    def _create_dock(self) -> None:
        from qgis.PyQt.QtCore import Qt  # type: ignore
        from qgis.PyQt.QtWidgets import QDockWidget  # type: ignore

        from .cartography.qtcompat import qt_enum
        from .ui.panel import SigmaiPanel
        from .ui.strings import translate
        from .ui.theme import get_sigmai_stylesheet

        self.panel = SigmaiPanel(self)
        self.panel.setStyleSheet(get_sigmai_stylesheet(self._ui_scale()))

        # Um painel acoplável, e não um diálogo modal: o usuário precisa ver o
        # estado da ponte enquanto trabalha no mapa, não em vez disso.
        self.dock = QDockWidget(translate(self.language, "window_title"), self.iface.mainWindow())
        self.dock.setObjectName("SigmaiDock")
        self.dock.setWidget(self.panel)
        self.dock.setMinimumWidth(380)
        try:
            area = qt_enum(Qt, "DockWidgetArea", "RightDockWidgetArea")
            self.iface.addDockWidget(area, self.dock)
        except Exception:
            self.dock.setFloating(True)

    def _ui_scale(self) -> float:
        try:
            from qgis.PyQt.QtWidgets import QApplication  # type: ignore

            dpi = QApplication.primaryScreen().logicalDotsPerInch()
            return max(0.85, min(1.8, float(dpi) / 96.0))
        except Exception:
            return 1.0

    # -- ponte ------------------------------------------------------------
    def start_bridge(self) -> None:
        try:
            self.server.start()
            self._write_session_file()
            self.last_error = ""
            self._message(self._tr("msg_started", host=self.server.host, port=self.server.port))
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._message(f"{self._tr('msg_start_failed')}: {exc}", level="critical")
        self._refresh_panel()

    def stop_bridge(self, quiet: bool = False) -> None:
        self.server.stop()
        invalidate_session_file()
        if not quiet:
            self._message(self._tr("msg_stopped"))
        self._refresh_panel()

    def regenerate_token(self) -> None:
        was_running = self.server.running
        if was_running:
            self.server.stop()
        self.token = generate_token()
        self.server.token = self.token
        self._store_token(self.token)
        self.session_id = generate_pairing_code()
        if was_running:
            self.start_bridge()
        self._refresh_panel()

    def _write_session_file(self) -> None:
        if not bool(self.settings_get("write_session_file", True)):
            return
        payload = build_session_payload(
            host=self.server.host,
            # A porta real, e não a constante: com o fallback de porta a ponte
            # pode ter subido em 8766, e um arquivo de sessão apontando para
            # 8765 deixaria o cliente batendo na porta errada.
            port=self.server.port,
            token=self.token,
            qgis_version=self.server.qgis_version,
            plugin_version=self.plugin_version(),
            running=self.server.running,
            session_id=self.session_id,
        )
        self.session_file = write_session_file(payload)
        cleanup_old_sessions()

    # -- protocolo esperado pelo painel -----------------------------------
    def session_file_path(self) -> Path:
        return session_file_path()

    def settings_get(self, key: str, default: Any = None) -> Any:
        fallback = SETTINGS_DEFAULTS.get(key, default)
        try:
            from qgis.core import QgsSettings  # type: ignore

            settings = QgsSettings()
            if isinstance(fallback, bool):
                return settings.value(f"{SETTINGS_PREFIX}/{key}", fallback, type=bool)
            if isinstance(fallback, int):
                return settings.value(f"{SETTINGS_PREFIX}/{key}", fallback, type=int)
            return settings.value(f"{SETTINGS_PREFIX}/{key}", fallback, type=str)
        except Exception:
            return fallback

    def settings_set(self, key: str, value: Any) -> None:
        try:
            from qgis.core import QgsSettings  # type: ignore

            QgsSettings().setValue(f"{SETTINGS_PREFIX}/{key}", value)
        except Exception:
            pass

    def set_language(self, language: str) -> None:
        self.language = "en" if language == "en" else "pt-BR"
        self.settings_set("ui_language", self.language)
        if self.dock is not None:
            from .ui.strings import translate

            self.dock.setWindowTitle(translate(self.language, "window_title"))

    def copy_to_clipboard(self, text: str) -> None:
        try:
            from qgis.PyQt.QtWidgets import QApplication  # type: ignore

            QApplication.clipboard().setText(str(text))
        except Exception:
            pass

    def open_path(self, path: str) -> None:
        target = Path(str(path)).expanduser()
        folder = target if target.is_dir() else target.parent
        self._open_url(folder)

    def open_diagnostics(self) -> None:
        try:
            sessions_dir().mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._open_url(sessions_dir())

    def _open_url(self, folder: Path) -> None:
        try:
            from qgis.PyQt.QtCore import QUrl  # type: ignore
            from qgis.PyQt.QtGui import QDesktopServices  # type: ignore

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception as exc:
            self.last_error = str(exc)

    def utc_now(self) -> str:
        return _utc_now()

    def toggle_dev_mode(self) -> None:
        if self.server.unsafe_developer_mode:
            self.server.set_unsafe_developer_mode(False)
            self._message(self._tr("dev_off"))
            return
        try:
            from qgis.PyQt.QtWidgets import QInputDialog, QLineEdit, QMessageBox  # type: ignore
        except Exception:
            return
        parent = self.panel or self.iface.mainWindow()
        QMessageBox.warning(parent, self._tr("dev_dialog_title"), self._tr("dev_warning"))
        from .cartography.qtcompat import qt_enum

        echo_normal = qt_enum(QLineEdit, "EchoMode", "Normal")
        text, accepted = QInputDialog.getText(
            parent, self._tr("dev_dialog_title"), self._tr("dev_dialog_prompt"), echo_normal, ""
        )
        if accepted and str(text).strip().upper() == "SIM":
            self.server.set_unsafe_developer_mode(True)
            self._message(self._tr("dev_on"), level="critical")

    # -- autoteste --------------------------------------------------------
    def run_self_test(self) -> list[dict[str, Any]]:
        """Percorre a ponte como um cliente de IA faria.

        Cada item devolve ``ok`` e uma explicação. É o que substitui a
        pergunta "por que o Claude não conecta?" por uma linha que diz onde
        parou.
        """
        results: list[dict[str, Any]] = []

        if not self.server.running:
            results.append({"ok": False, "label": "Ponte local", "detail": "A ponte está desligada. Inicie no passo 1."})
            return results

        base = f"http://{self.server.host}:{self.server.port}"
        results.append(self._probe_health(base))
        results.append(self._probe_auth(base))
        results.append(self._probe_command(base))
        results.append(self._probe_session_file())
        results.append(self._probe_mcp_server())
        results.append(self._probe_consent())
        return results

    def _probe_health(self, base: str) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "label": "Ponte local", "detail": f"responde em {self.server.host}:{self.server.port} (plugin {payload.get('plugin_version')})"}
        except Exception as exc:
            return {"ok": False, "label": "Ponte local", "detail": f"sem resposta: {exc}"}

    def _probe_auth(self, base: str) -> dict[str, Any]:
        body = json.dumps({"action": "status"}).encode("utf-8")
        request = urllib.request.Request(base + "/command", data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(request, timeout=4)
            return {"ok": False, "label": "Autenticação", "detail": "a ponte aceitou uma requisição SEM token — isto não deveria acontecer"}
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return {"ok": True, "label": "Autenticação", "detail": "requisição sem token é recusada, como esperado"}
            return {"ok": False, "label": "Autenticação", "detail": f"resposta inesperada HTTP {exc.code}"}
        except Exception as exc:
            return {"ok": False, "label": "Autenticação", "detail": str(exc)}

    def _probe_command(self, base: str) -> dict[str, Any]:
        body = json.dumps({"action": "get_project_overview", "params": {"include_fields": False}}).encode("utf-8")
        request = urllib.request.Request(
            base + "/command", data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not payload.get("ok"):
                return {"ok": False, "label": "Projeto QGIS", "detail": str((payload.get("errors") or [{}])[0].get("message", ""))[:120]}
            data = payload.get("data") or {}
            return {
                "ok": True,
                "label": "Projeto QGIS",
                "detail": f"{data.get('layer_count', 0)} camada(s), CRS {data.get('project_crs') or 'não definido'}",
            }
        except Exception as exc:
            return {"ok": False, "label": "Projeto QGIS", "detail": str(exc)}

    def _probe_session_file(self) -> dict[str, Any]:
        if not bool(self.settings_get("write_session_file", True)):
            return {"ok": False, "label": "Arquivo de sessão", "detail": "desligado em Avançado; os clientes de IA não vão encontrar a ponte sozinhos"}
        path = session_file_path()
        if not path.exists():
            return {"ok": False, "label": "Arquivo de sessão", "detail": f"não encontrado em {path}"}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "label": "Arquivo de sessão", "detail": f"ilegível: {exc}"}
        if int(data.get("port", 0)) != int(self.server.port):
            return {"ok": False, "label": "Arquivo de sessão", "detail": f"aponta para a porta {data.get('port')}, mas a ponte está na {self.server.port}"}
        return {"ok": True, "label": "Arquivo de sessão", "detail": "gravado e coerente com a ponte"}

    def _probe_mcp_server(self) -> dict[str, Any]:
        server = Path(__file__).resolve().parent / "mcp" / "sigmai_mcp.py"
        if not server.exists():
            return {"ok": False, "label": "Servidor MCP", "detail": f"arquivo ausente: {server}"}
        from .ui.client_configs import python_executable

        executable = python_executable()
        if not Path(executable).exists() and executable not in {"python", "python3"}:
            return {"ok": False, "label": "Servidor MCP", "detail": f"interpretador não encontrado: {executable}"}
        return {"ok": True, "label": "Servidor MCP", "detail": f"{server.name} pronto, com {Path(executable).name}"}

    def _probe_consent(self) -> dict[str, Any]:
        status = self.consent.status()
        if status["mode"] == MODE_READ_ONLY:
            return {
                "ok": False,
                "label": "Modo de acesso",
                "detail": "somente leitura: a IA pode inspecionar e simular, mas não gerar mapas. Mude na aba Acesso quando quiser.",
            }
        return {"ok": True, "label": "Modo de acesso", "detail": status["mode_label"]}

    # -- consentimento ----------------------------------------------------
    def _prompt_for_consent(self, request: Any) -> tuple[str, bool]:
        """Diálogo de confirmação, executado na thread da interface do QGIS."""
        try:
            from qgis.PyQt.QtWidgets import QCheckBox, QMessageBox  # type: ignore
        except Exception:
            return (DECISION_DENIED, False)

        from .ui.strings import translate

        box = QMessageBox(self.panel or self.iface.mainWindow())
        box.setWindowTitle(translate(self.language, "consent_dialog_title"))
        from .cartography.qtcompat import qt_enum

        box.setIcon(qt_enum(QMessageBox, "Icon", "Question"))
        box.setText(f"<b>{request.category}</b> — {request.category_description}")
        box.setInformativeText(request.summary())
        remember = QCheckBox(translate(self.language, "consent_allow_category"))
        box.setCheckBox(remember)
        allow = box.addButton(translate(self.language, "consent_allow"), qt_enum(QMessageBox, "ButtonRole", "AcceptRole"))
        box.addButton(translate(self.language, "consent_deny"), qt_enum(QMessageBox, "ButtonRole", "RejectRole"))
        box.exec() if hasattr(box, "exec") else box.exec_()
        allowed = box.clickedButton() is allow
        self._refresh_panel()
        return (DECISION_ALLOWED if allowed else DECISION_DENIED, bool(remember.isChecked()))

    def _restore_consent_settings(self) -> None:
        mode = str(self.settings_get("consent_mode", MODE_READ_ONLY))
        self.consent.set_mode(mode if mode in MODES else MODE_READ_ONLY)
        roots = str(self.settings_get("output_roots", "") or "")
        if roots:
            self.consent.set_output_roots([item for item in roots.split("|") if item])
        for name in ("writes_per_session", "exports_per_session", "processing_runs_per_session"):
            self.consent.set_limit(name, int(self.settings_get(f"limit_{name}", SETTINGS_DEFAULTS[f"limit_{name}"])))

    # -- token ------------------------------------------------------------
    def _load_or_create_token(self) -> str:
        """Token estável entre sessões, se o usuário quiser.

        Um token novo a cada abertura do QGIS obriga a refazer a configuração
        do cliente de IA toda vez — era a principal causa de "ontem funcionava".
        O token fica no QgsSettings do perfil do usuário, mesmo nível de
        proteção do arquivo de sessão que já o continha em texto puro.
        """
        if not bool(self.settings_get("persist_token", True)):
            return generate_token()
        stored = str(self.settings_get("bridge_token", "") or "")
        if len(stored) >= 32:
            return stored
        token = generate_token()
        self._store_token(token)
        return token

    def _store_token(self, token: str) -> None:
        if bool(self.settings_get("persist_token", True)):
            self.settings_set("bridge_token", token)

    # -- auxiliares -------------------------------------------------------
    def plugin_version(self) -> str:
        metadata = Path(__file__).resolve().parent / "metadata.txt"
        try:
            for line in metadata.read_text(encoding="utf-8").splitlines():
                if line.lower().startswith("version="):
                    return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return "0.0.0"

    def _tr(self, key: str, **kwargs: Any) -> str:
        from .ui.strings import translate

        return translate(self.language, key, **kwargs)

    def _refresh_panel(self) -> None:
        if self.panel is not None:
            try:
                self.panel.refresh()
            except Exception:
                pass

    def _message(self, text: str, level: str = "info") -> None:
        try:
            from qgis.core import Qgis  # type: ignore

            from .cartography.qtcompat import qt_enum

            severity = qt_enum(Qgis, "MessageLevel", "Critical" if level == "critical" else "Info")
            self.iface.messageBar().pushMessage("SIGMAI", text, level=severity, duration=6)
        except Exception:
            pass
