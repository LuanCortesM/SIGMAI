from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .bridge_server import SIGMAIServer
from .security import DEFAULT_HOST, DEFAULT_PORT, generate_token
from .session import build_session_payload, cleanup_old_sessions, generate_pairing_code, invalidate_session_file, session_file_path, sessions_dir, write_session_file
from .theme import get_sigmai_stylesheet


class SIGMAIPlugin:
    def __init__(self, iface: Any):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.last_error = ""
        self.session_file = None
        self.session_id = generate_pairing_code()
        self.token = generate_token()
        self.language = self._ui_language()
        self.server = SIGMAIServer(
            iface=iface,
            host=DEFAULT_HOST,
            port=DEFAULT_PORT,
            token=self.token,
            log_dir=Path(__file__).resolve().parent / "logs",
        )

    def initGui(self) -> None:
        try:
            from qgis.PyQt.QtCore import QTimer  # type: ignore
            from qgis.PyQt.QtWidgets import QAction  # type: ignore
        except Exception:
            return
        from qgis.PyQt.QtGui import QIcon  # type: ignore

        icon_path = str(Path(__file__).resolve().parent / "icons" / "sigmai_icon.png")
        self.action = QAction(QIcon(icon_path), "SIGMAI", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dialog)
        self.iface.addPluginToMenu("&SIGMAI", self.action)
        self.iface.addToolBarIcon(self.action)
        if self._auto_start_enabled():
            QTimer.singleShot(1500, self.start_bridge)

    def unload(self) -> None:
        self.server.stop()
        if self.action is not None:
            self.iface.removePluginMenu("&SIGMAI", self.action)
            self.iface.removeToolBarIcon(self.action)

    def show_dialog(self) -> None:
        if self.dialog is None:
            self.dialog = self._create_dialog()
        self._refresh_dialog()
        self.dialog.show()
        self.dialog.raise_()

    def _create_dialog(self):
        from qgis.PyQt.QtWidgets import (  # type: ignore
            QDialog,
            QFormLayout,
            QFrame,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QSizePolicy,
            QTextEdit,
            QVBoxLayout,
            QCheckBox,
            QMessageBox,
            QInputDialog,
        )
        from qgis.PyQt.QtCore import Qt  # type: ignore
        from qgis.PyQt.QtGui import QIcon, QPixmap  # type: ignore

        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("SIGMAI - Secure GIS-AI Interface")
        dialog.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "icons" / "sigmai_icon.png")))
        dialog.resize(760, 620)
        dialog.setStyleSheet(get_sigmai_stylesheet())
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 18, 18)
        header_layout.setSpacing(18)
        logo_label = QLabel()
        logo_label.setObjectName("logoPanel")
        logo_pixmap = QPixmap(str(Path(__file__).resolve().parent / "icons" / "sigmai_logo_full.png"))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaledToHeight(74, Qt.SmoothTransformation))
        logo_label.setFixedHeight(92)
        logo_label.setMinimumWidth(190)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        dialog.title_label = QLabel("SIGMAI")
        dialog.title_label.setObjectName("brandTitle")
        dialog.subtitle_label = QLabel("Secure GIS-AI Interface")
        dialog.subtitle_label.setObjectName("brandSubtitle")
        dialog.context_label = QLabel("Local secure bridge between AI agents and QGIS")
        dialog.context_label.setObjectName("brandContext")
        dialog.author_label = QLabel("Plugin author: MACIEL, L. S. C.")
        dialog.author_label.setObjectName("brandContext")
        title_box.addWidget(dialog.title_label)
        title_box.addWidget(dialog.subtitle_label)
        title_box.addWidget(dialog.context_label)
        title_box.addWidget(dialog.author_label)
        title_box.addStretch(1)
        dialog.header_status = QLabel("Bridge Offline")
        dialog.header_status.setObjectName("statusBadgeOffline")
        dialog.language_button = QPushButton("PT-BR")
        dialog.language_button.setObjectName("languageButton")
        dialog.language_button.clicked.connect(self._toggle_language)
        header_tools = QVBoxLayout()
        header_tools.setSpacing(8)
        header_tools.addWidget(dialog.language_button, 0, Qt.AlignRight)
        header_tools.addWidget(dialog.header_status, 0, Qt.AlignRight)
        header_tools.addStretch(1)
        header_layout.addWidget(logo_label)
        header_layout.addLayout(title_box, 1)
        header_layout.addLayout(header_tools, 0)
        layout.addWidget(header)

        status_group = QGroupBox("Bridge Status")
        dialog.status_group = status_group
        status_layout = QVBoxLayout(status_group)
        status_hint = QLabel("Local-only bridge state and secure QGIS endpoint.")
        dialog.status_hint = status_hint
        status_hint.setObjectName("sectionHint")
        status_layout.addWidget(status_hint)
        status_form = QFormLayout()
        form = QFormLayout()
        dialog.host_value = QLabel(DEFAULT_HOST)
        dialog.port_value = QLabel(str(DEFAULT_PORT))
        dialog.token_value = QLineEdit(self.token)
        dialog.token_value.setReadOnly(True)
        dialog.token_value.setProperty("technical", True)
        dialog.pairing_value = QLineEdit(self.session_id)
        dialog.pairing_value.setReadOnly(True)
        dialog.pairing_value.setProperty("technical", True)
        dialog.status_value = QLabel("Stopped")
        dialog.autostart_value = QCheckBox("Start bridge automatically when QGIS starts")
        dialog.autostart_value.setChecked(self._auto_start_enabled())
        dialog.autostart_value.toggled.connect(self._set_auto_start_enabled)
        dialog.write_session_value = QCheckBox("Write local session file for AI clients")
        dialog.write_session_value.setChecked(self._write_session_enabled())
        dialog.write_session_value.toggled.connect(self._set_write_session_enabled)
        dialog.session_path_value = QLineEdit(str(session_file_path()))
        dialog.session_path_value.setReadOnly(True)
        dialog.session_path_value.setProperty("technical", True)
        dialog.last_error_value = QLabel("")
        dialog.status_form = status_form
        status_form.addRow("Status", dialog.status_value)
        status_form.addRow("Host", dialog.host_value)
        status_form.addRow("Port", dialog.port_value)
        status_form.addRow("Auto-start", dialog.autostart_value)
        status_layout.addLayout(status_form)
        layout.addWidget(status_group)

        session_group = QGroupBox("Secure Session")
        dialog.session_group = session_group
        session_layout = QVBoxLayout(session_group)
        session_hint = QLabel("Token protected session discovery for local AI clients.")
        dialog.session_hint = session_hint
        session_hint.setObjectName("sectionHint")
        session_layout.addWidget(session_hint)
        form = QFormLayout()
        dialog.session_form = form
        form.addRow("Token", dialog.token_value)
        form.addRow("Pairing code", dialog.pairing_value)
        form.addRow("Write session file", dialog.write_session_value)
        form.addRow("Session path", dialog.session_path_value)
        form.addRow("Last error", dialog.last_error_value)
        session_layout.addLayout(form)
        layout.addWidget(session_group)

        dev_group = QGroupBox("Developer Mode")
        dialog.dev_group = dev_group
        dev_layout = QVBoxLayout(dev_group)
        dev_hint = QLabel(
            "Off by default. Enables explicit QGIS Python execution for plugin development after typing SIM."
        )
        dialog.dev_hint = dev_hint
        dev_hint.setObjectName("sectionHint")
        dialog.dev_status_value = QLabel("DEV Mode Off")
        dialog.dev_status_value.setObjectName("devBadgeOff")
        dialog.dev_warning_value = QLabel(
            "Esse modo tem riscos de corromper o seu QGIS. Use com cuidado, pois mexe direto no Python da ferramenta."
        )
        dialog.dev_warning_value.setWordWrap(True)
        dialog.dev_warning_value.setObjectName("dangerText")
        dialog.dev_toggle_button = QPushButton("DEV MODE OFF")
        dialog.dev_toggle_button.setObjectName("devDangerButtonOff")
        dialog.dev_toggle_button.clicked.connect(self._toggle_dev_mode)
        dev_top = QHBoxLayout()
        dev_top.addWidget(dialog.dev_status_value)
        dev_top.addStretch(1)
        dev_top.addWidget(dialog.dev_toggle_button)
        dev_layout.addWidget(dev_hint)
        dev_layout.addLayout(dev_top)
        dev_layout.addWidget(dialog.dev_warning_value)
        layout.addWidget(dev_group)

        buttons_primary = QHBoxLayout()
        buttons_secondary = QHBoxLayout()
        dialog.start_button = QPushButton("Start Bridge")
        dialog.start_button.setObjectName("primaryButton")
        dialog.stop_button = QPushButton("Stop Bridge")
        dialog.stop_button.setObjectName("dangerButton")
        dialog.refresh_button = QPushButton("Status")
        dialog.refresh_button.setObjectName("secondaryButton")
        dialog.copy_token_button = QPushButton("Copy Token")
        dialog.copy_token_button.setObjectName("secondaryButton")
        dialog.copy_pairing_button = QPushButton("Copy Pairing Code")
        dialog.copy_pairing_button.setObjectName("secondaryButton")
        dialog.regenerate_token_button = QPushButton("Regenerate Token")
        dialog.regenerate_token_button.setObjectName("secondaryButton")
        dialog.regenerate_session_button = QPushButton("Regenerate Session")
        dialog.regenerate_session_button.setObjectName("secondaryButton")
        dialog.copy_session_path_button = QPushButton("Copy Session Path")
        dialog.copy_session_path_button.setObjectName("secondaryButton")
        dialog.copy_cli_button = QPushButton("Copy CLI Command")
        dialog.copy_cli_button.setObjectName("secondaryButton")
        dialog.copy_mcp_button = QPushButton("Copy MCP Hint")
        dialog.copy_mcp_button.setObjectName("secondaryButton")
        dialog.open_diagnostics_button = QPushButton("Open Diagnostics Folder")
        dialog.open_diagnostics_button.setObjectName("secondaryButton")
        dialog.start_button.clicked.connect(self.start_bridge)
        dialog.stop_button.clicked.connect(self.stop_bridge)
        dialog.refresh_button.clicked.connect(self._refresh_dialog)
        dialog.copy_token_button.clicked.connect(self._copy_token)
        dialog.copy_pairing_button.clicked.connect(self._copy_pairing_code)
        dialog.regenerate_token_button.clicked.connect(self._regenerate_token)
        dialog.regenerate_session_button.clicked.connect(self._regenerate_session)
        dialog.copy_session_path_button.clicked.connect(self._copy_session_path)
        dialog.copy_cli_button.clicked.connect(self._copy_cli_command)
        dialog.copy_mcp_button.clicked.connect(self._copy_mcp_hint)
        dialog.open_diagnostics_button.clicked.connect(self._open_diagnostics_folder)
        buttons_primary.addWidget(dialog.start_button)
        buttons_primary.addWidget(dialog.stop_button)
        buttons_primary.addWidget(dialog.refresh_button)
        buttons_primary.addWidget(dialog.regenerate_token_button)
        buttons_primary.addWidget(dialog.regenerate_session_button)
        buttons_primary.addStretch(1)
        buttons_secondary.addWidget(dialog.copy_token_button)
        buttons_secondary.addWidget(dialog.copy_pairing_button)
        buttons_secondary.addWidget(dialog.copy_session_path_button)
        buttons_secondary.addWidget(dialog.copy_cli_button)
        buttons_secondary.addWidget(dialog.copy_mcp_button)
        buttons_secondary.addWidget(dialog.open_diagnostics_button)
        buttons_secondary.addStretch(1)
        layout.addLayout(buttons_primary)
        layout.addLayout(buttons_secondary)

        docs_group = QGroupBox("AI Clients and Diagnostics")
        dialog.docs_group = docs_group
        docs_layout = QVBoxLayout(docs_group)
        docs_hint = QLabel("Copy-ready commands for Codex, MCP and local diagnostics.")
        dialog.docs_hint = docs_hint
        docs_hint.setObjectName("sectionHint")
        docs_layout.addWidget(docs_hint)
        dialog.docs = QTextEdit()
        dialog.docs.setProperty("technical", True)
        dialog.docs.setReadOnly(True)
        dialog.docs.setMinimumHeight(120)
        docs_layout.addWidget(dialog.docs)
        layout.addWidget(docs_group)
        self._apply_language()
        return dialog

    def start_bridge(self) -> None:
        try:
            self.server.start()
            self._write_session_file()
            self.last_error = ""
            self._message(self._tr("msg_bridge_started"))
        except Exception as exc:
            self.last_error = str(exc)
            self._message(f"{self._tr('msg_bridge_start_failed')}: {exc}", level="critical")
        self._refresh_dialog()

    def stop_bridge(self) -> None:
        self.server.stop()
        invalidate_session_file()
        self._message(self._tr("msg_bridge_stopped"))
        self._refresh_dialog()

    def _refresh_dialog(self) -> None:
        if self.dialog is None:
            return
        status = self.server.status()
        running = bool(status["running"])
        self.dialog.status_value.setText(self._tr("bridge_online") if running else self._tr("bridge_offline"))
        self.dialog.header_status.setText(self._tr("bridge_online") if running else self._tr("bridge_offline"))
        self.dialog.header_status.setObjectName("statusBadgeOnline" if running else "statusBadgeOffline")
        self.dialog.header_status.style().unpolish(self.dialog.header_status)
        self.dialog.header_status.style().polish(self.dialog.header_status)
        self.dialog.token_value.setText(self.token)
        self.dialog.pairing_value.setText(self.session_id)
        self.dialog.session_path_value.setText(str(session_file_path()))
        self.dialog.last_error_value.setText(self.last_error)
        dev_enabled = bool(self.server.unsafe_developer_mode)
        self.dialog.dev_status_value.setText(self._tr("dev_active") if dev_enabled else self._tr("dev_off"))
        self.dialog.dev_status_value.setObjectName("devBadgeOn" if dev_enabled else "devBadgeOff")
        self.dialog.dev_status_value.style().unpolish(self.dialog.dev_status_value)
        self.dialog.dev_status_value.style().polish(self.dialog.dev_status_value)
        self.dialog.dev_toggle_button.setText(self._tr("dev_button_on") if dev_enabled else self._tr("dev_button_off"))
        self.dialog.dev_toggle_button.setObjectName("devDangerButtonOn" if dev_enabled else "devDangerButtonOff")
        self.dialog.dev_toggle_button.style().unpolish(self.dialog.dev_toggle_button)
        self.dialog.dev_toggle_button.style().polish(self.dialog.dev_toggle_button)
        self._apply_language()
        self.dialog.docs.setPlainText(
            "Endpoint: http://127.0.0.1:8765/command\n"
            f"{self._tr('docs_header')}: Authorization: Bearer TOKEN\n"
            f"{self._tr('docs_autotest')}: python tools\\sigmai_autotest.py --run-integration\n"
            f"{self._tr('docs_pairing')}: {self.session_id}\n"
            f"{self._tr('docs_docs')}: SIGMAI README.md, codex_plugin/README.md\n"
            f"{self._tr('docs_logs')}: {status['log_path']}\n"
            f"{self._tr('docs_session')}: {session_file_path()}\n"
            f"{self._tr('docs_dev_mode')}: {self._tr('docs_dev_on') if dev_enabled else self._tr('docs_dev_off')}"
        )

    def _toggle_dev_mode(self) -> None:
        if self.server.unsafe_developer_mode:
            self.server.set_unsafe_developer_mode(False)
            self._message(self._tr("msg_dev_disabled"))
            self._refresh_dialog()
            return
        try:
            from qgis.PyQt.QtWidgets import QInputDialog, QLineEdit, QMessageBox  # type: ignore
        except Exception:
            return
        warning = self._tr("dev_warning_dialog")
        QMessageBox.warning(self.dialog, self._tr("dev_dialog_title"), warning)
        text, ok = QInputDialog.getText(self.dialog, self._tr("dev_enable_title"), self._tr("dev_enable_prompt"), QLineEdit.Normal, "")
        if ok and text.strip().upper() == "SIM":
            self.server.set_unsafe_developer_mode(True)
            self._message(self._tr("msg_dev_enabled"), level="critical")
        else:
            self._message(self._tr("msg_dev_not_enabled"))
        self._refresh_dialog()

    def _translations(self) -> dict[str, dict[str, str]]:
        return {
            "en": {
                "window_title": "SIGMAI - Secure GIS-AI Interface",
                "subtitle": "Secure GIS-AI Interface",
                "context": "Local secure bridge between AI agents and QGIS",
                "author": "Plugin author: MACIEL, L. S. C.",
                "language_button": "PT-BR",
                "bridge_online": "Bridge Online",
                "bridge_offline": "Bridge Offline",
                "status_group": "Bridge Status",
                "status_hint": "Local-only bridge state and secure QGIS endpoint.",
                "status": "Status",
                "host": "Host",
                "port": "Port",
                "auto_start": "Auto-start",
                "autostart_checkbox": "Start bridge automatically when QGIS starts",
                "session_group": "Secure Session",
                "session_hint": "Token protected session discovery for local AI clients.",
                "pairing_code": "Pairing code",
                "write_session_file": "Write session file",
                "write_session_checkbox": "Write local session file for AI clients",
                "session_path": "Session path",
                "last_error": "Last error",
                "dev_group": "Developer Mode",
                "dev_hint": "Off by default. Enables explicit QGIS Python execution for plugin development after typing SIM.",
                "dev_warning": "This mode can corrupt your QGIS. Use with care because it works directly with the tool's Python runtime.",
                "dev_off": "DEV Mode Off",
                "dev_active": "DEV Mode Active",
                "dev_button_off": "DEV MODE OFF",
                "dev_button_on": "DEV MODE ON - click to disable",
                "start_bridge": "Start Bridge",
                "stop_bridge": "Stop Bridge",
                "refresh": "Status",
                "copy_token": "Copy Token",
                "copy_pairing": "Copy Pairing Code",
                "regen_token": "Regenerate Token",
                "regen_session": "Regenerate Session",
                "copy_session": "Copy Session Path",
                "copy_cli": "Copy CLI Command",
                "copy_mcp": "Copy MCP Hint",
                "open_diag": "Open Diagnostics Folder",
                "docs_group": "AI Clients and Diagnostics",
                "docs_hint": "Copy-ready commands for Codex, MCP and local diagnostics.",
                "dev_dialog_title": "SIGMAI DEV Mode",
                "dev_enable_title": "Enable DEV Mode",
                "dev_enable_prompt": "Type SIM to enable:",
                "dev_warning_dialog": "This mode can corrupt your QGIS.\n\nUse with care because it works directly with the tool's Python runtime.\nIt exists to program, test and debug plugins inside QGIS.\n\nTo enable it, type SIM.",
                "msg_dev_disabled": "SIGMAI DEV mode disabled.",
                "msg_dev_enabled": "SIGMAI DEV mode enabled. Use with care.",
                "msg_dev_not_enabled": "SIGMAI DEV mode was not enabled.",
                "msg_bridge_started": "SIGMAI bridge started.",
                "msg_bridge_stopped": "SIGMAI bridge stopped.",
                "msg_bridge_start_failed": "Could not start SIGMAI bridge",
                "docs_header": "Header",
                "docs_autotest": "Autotest",
                "docs_pairing": "Pairing",
                "docs_docs": "Docs",
                "docs_logs": "Logs",
                "docs_session": "Session",
                "docs_dev_mode": "DEV mode",
                "docs_dev_on": "ON - QGIS Python execution enabled",
                "docs_dev_off": "OFF",
            },
            "pt-BR": {
                "window_title": "SIGMAI - Interface Segura GIS-IA",
                "subtitle": "Interface Segura GIS-IA",
                "context": "Bridge local e segura entre agentes de IA e o QGIS",
                "author": "Autor do plugin: MACIEL, L. S. C.",
                "language_button": "ENG",
                "bridge_online": "Bridge Online",
                "bridge_offline": "Bridge Offline",
                "status_group": "Status da Bridge",
                "status_hint": "Estado da bridge local e endpoint seguro do QGIS.",
                "status": "Status",
                "host": "Host",
                "port": "Porta",
                "auto_start": "Inicialização automática",
                "autostart_checkbox": "Iniciar a bridge automaticamente com o QGIS",
                "session_group": "Sessão Segura",
                "session_hint": "Descoberta de sessão protegida por token para clientes de IA locais.",
                "pairing_code": "Código de pareamento",
                "write_session_file": "Gravar sessão",
                "write_session_checkbox": "Gravar arquivo de sessão local para clientes de IA",
                "session_path": "Caminho da sessão",
                "last_error": "Último erro",
                "dev_group": "Modo Desenvolvedor",
                "dev_hint": "Desligado por padrão. Libera execução explícita de Python do QGIS para desenvolvimento de plugins após digitar SIM.",
                "dev_warning": "Esse modo tem riscos de corromper o seu QGIS. Use com cuidado, pois mexe direto no Python da ferramenta.",
                "dev_off": "Modo DEV Desligado",
                "dev_active": "Modo DEV Ativo",
                "dev_button_off": "MODO DEV DESLIGADO",
                "dev_button_on": "MODO DEV LIGADO - clique para desligar",
                "start_bridge": "Iniciar Bridge",
                "stop_bridge": "Parar Bridge",
                "refresh": "Status",
                "copy_token": "Copiar Token",
                "copy_pairing": "Copiar Código",
                "regen_token": "Regenerar Token",
                "regen_session": "Regenerar Sessão",
                "copy_session": "Copiar Caminho da Sessão",
                "copy_cli": "Copiar Comando CLI",
                "copy_mcp": "Copiar Dica MCP",
                "open_diag": "Abrir Pasta de Diagnósticos",
                "docs_group": "Clientes de IA e Diagnósticos",
                "docs_hint": "Comandos prontos para copiar para Codex, MCP e diagnósticos locais.",
                "dev_dialog_title": "Modo DEV do SIGMAI",
                "dev_enable_title": "Ativar Modo DEV",
                "dev_enable_prompt": "Digite SIM para ativar:",
                "dev_warning_dialog": "Esse modo tem riscos de corromper o seu QGIS.\n\nUse com cuidado, pois mexe direto no Python da ferramenta.\nEle existe para programar, testar e depurar plugins dentro do QGIS.\n\nPara ativar, digite SIM.",
                "msg_dev_disabled": "Modo DEV do SIGMAI desativado.",
                "msg_dev_enabled": "Modo DEV do SIGMAI ativado. Use com cuidado.",
                "msg_dev_not_enabled": "O modo DEV do SIGMAI não foi ativado.",
                "msg_bridge_started": "Bridge do SIGMAI iniciada.",
                "msg_bridge_stopped": "Bridge do SIGMAI parada.",
                "msg_bridge_start_failed": "Não foi possível iniciar a Bridge do SIGMAI",
                "docs_header": "Cabeçalho",
                "docs_autotest": "Autoteste",
                "docs_pairing": "Pareamento",
                "docs_docs": "Documentação",
                "docs_logs": "Logs",
                "docs_session": "Sessão",
                "docs_dev_mode": "Modo DEV",
                "docs_dev_on": "LIGADO - execução de Python do QGIS habilitada",
                "docs_dev_off": "DESLIGADO",
            },
        }

    def _tr(self, key: str) -> str:
        return self._translations().get(self.language, self._translations()["en"]).get(key, key)

    def _ui_language(self) -> str:
        try:
            from qgis.core import QgsSettings  # type: ignore

            value = QgsSettings().value("SIGMAI/ui_language", "en", type=str)
            return "pt-BR" if value == "pt-BR" else "en"
        except Exception:
            return "en"

    def _set_ui_language(self, language: str) -> None:
        self.language = "pt-BR" if language == "pt-BR" else "en"
        try:
            from qgis.core import QgsSettings  # type: ignore

            QgsSettings().setValue("SIGMAI/ui_language", self.language)
        except Exception:
            pass

    def _toggle_language(self) -> None:
        self._set_ui_language("pt-BR" if self.language == "en" else "en")
        self._apply_language()
        self._refresh_dialog()

    def _set_form_label(self, form: Any, field: Any, text: str) -> None:
        try:
            label = form.labelForField(field)
            if label is not None:
                label.setText(text)
        except Exception:
            pass

    def _apply_language(self) -> None:
        if self.dialog is None:
            return
        self.dialog.setWindowTitle(self._tr("window_title"))
        self.dialog.subtitle_label.setText(self._tr("subtitle"))
        self.dialog.context_label.setText(self._tr("context"))
        self.dialog.author_label.setText(self._tr("author"))
        self.dialog.language_button.setText(self._tr("language_button"))
        self.dialog.status_group.setTitle(self._tr("status_group"))
        self.dialog.status_hint.setText(self._tr("status_hint"))
        self._set_form_label(self.dialog.status_form, self.dialog.status_value, self._tr("status"))
        self._set_form_label(self.dialog.status_form, self.dialog.host_value, self._tr("host"))
        self._set_form_label(self.dialog.status_form, self.dialog.port_value, self._tr("port"))
        self._set_form_label(self.dialog.status_form, self.dialog.autostart_value, self._tr("auto_start"))
        self.dialog.autostart_value.setText(self._tr("autostart_checkbox"))
        self.dialog.session_group.setTitle(self._tr("session_group"))
        self.dialog.session_hint.setText(self._tr("session_hint"))
        self._set_form_label(self.dialog.session_form, self.dialog.token_value, "Token")
        self._set_form_label(self.dialog.session_form, self.dialog.pairing_value, self._tr("pairing_code"))
        self._set_form_label(self.dialog.session_form, self.dialog.write_session_value, self._tr("write_session_file"))
        self._set_form_label(self.dialog.session_form, self.dialog.session_path_value, self._tr("session_path"))
        self._set_form_label(self.dialog.session_form, self.dialog.last_error_value, self._tr("last_error"))
        self.dialog.write_session_value.setText(self._tr("write_session_checkbox"))
        self.dialog.dev_group.setTitle(self._tr("dev_group"))
        self.dialog.dev_hint.setText(self._tr("dev_hint"))
        self.dialog.dev_warning_value.setText(self._tr("dev_warning"))
        self.dialog.start_button.setText(self._tr("start_bridge"))
        self.dialog.stop_button.setText(self._tr("stop_bridge"))
        self.dialog.refresh_button.setText(self._tr("refresh"))
        self.dialog.copy_token_button.setText(self._tr("copy_token"))
        self.dialog.copy_pairing_button.setText(self._tr("copy_pairing"))
        self.dialog.regenerate_token_button.setText(self._tr("regen_token"))
        self.dialog.regenerate_session_button.setText(self._tr("regen_session"))
        self.dialog.copy_session_path_button.setText(self._tr("copy_session"))
        self.dialog.copy_cli_button.setText(self._tr("copy_cli"))
        self.dialog.copy_mcp_button.setText(self._tr("copy_mcp"))
        self.dialog.open_diagnostics_button.setText(self._tr("open_diag"))
        self.dialog.docs_group.setTitle(self._tr("docs_group"))
        self.dialog.docs_hint.setText(self._tr("docs_hint"))

    def _write_session_file(self) -> None:
        if not self._write_session_enabled():
            return
        payload = build_session_payload(
            host=DEFAULT_HOST,
            port=DEFAULT_PORT,
            token=self.token,
            qgis_version=self.server._qgis_version(),
            plugin_version=self._plugin_version(),
            running=self.server.running,
            session_id=self.session_id,
        )
        self.session_file = write_session_file(payload)
        cleanup_old_sessions()

    def _auto_start_enabled(self) -> bool:
        try:
            from qgis.core import QgsSettings  # type: ignore

            settings = QgsSettings()
            return settings.value("SIGMAI/auto_start", settings.value("SIGMAI/auto_start", True, type=bool), type=bool)
        except Exception:
            return True

    def _set_auto_start_enabled(self, enabled: bool) -> None:
        try:
            from qgis.core import QgsSettings  # type: ignore

            QgsSettings().setValue("SIGMAI/auto_start", bool(enabled))
        except Exception:
            pass

    def _write_session_enabled(self) -> bool:
        try:
            from qgis.core import QgsSettings  # type: ignore

            settings = QgsSettings()
            return settings.value("SIGMAI/write_session_file", settings.value("SIGMAI/write_session_file", True, type=bool), type=bool)
        except Exception:
            return True

    def _set_write_session_enabled(self, enabled: bool) -> None:
        try:
            from qgis.core import QgsSettings  # type: ignore

            QgsSettings().setValue("SIGMAI/write_session_file", bool(enabled))
        except Exception:
            pass

    def _copy_token(self) -> None:
        try:
            from qgis.PyQt.QtWidgets import QApplication  # type: ignore

            QApplication.clipboard().setText(self.token)
        except Exception:
            pass

    def _copy_pairing_code(self) -> None:
        try:
            from qgis.PyQt.QtWidgets import QApplication  # type: ignore

            QApplication.clipboard().setText(self.session_id)
        except Exception:
            pass

    def _copy_session_path(self) -> None:
        try:
            from qgis.PyQt.QtWidgets import QApplication  # type: ignore

            QApplication.clipboard().setText(str(session_file_path()))
        except Exception:
            pass

    def _open_diagnostics_folder(self) -> None:
        try:
            from qgis.PyQt.QtCore import QUrl  # type: ignore
            from qgis.PyQt.QtGui import QDesktopServices  # type: ignore

            sessions_dir().mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(sessions_dir())))
        except Exception as exc:
            self.last_error = str(exc)
            self._refresh_dialog()

    def _regenerate_token(self) -> None:
        was_running = self.server.running
        if was_running:
            self.server.stop()
        self.token = generate_token()
        self.server.token = self.token
        if was_running:
            self.start_bridge()
        self._refresh_dialog()

    def _regenerate_session(self) -> None:
        was_running = self.server.running
        if was_running:
            self.server.stop()
        self.token = generate_token()
        self.session_id = generate_pairing_code()
        self.server.token = self.token
        if was_running:
            self.start_bridge()
        self._refresh_dialog()

    def _copy_cli_command(self) -> None:
        try:
            from qgis.PyQt.QtWidgets import QApplication  # type: ignore

            QApplication.clipboard().setText(f"python tools\\sigmai.py connect {self.session_id}")
        except Exception:
            pass

    def _copy_mcp_hint(self) -> None:
        try:
            from qgis.PyQt.QtWidgets import QApplication  # type: ignore

            QApplication.clipboard().setText(f"SIGMAI pairing code: {self.session_id}")
        except Exception:
            pass

    def _plugin_version(self) -> str:
        metadata_path = Path(__file__).resolve().parent / "metadata.txt"
        try:
            for line in metadata_path.read_text(encoding="utf-8").splitlines():
                if line.lower().startswith("version="):
                    return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return "0.1.0"

    def _message(self, text: str, level: str = "info") -> None:
        try:
            from qgis.core import Qgis  # type: ignore

            levels = {"info": Qgis.Info, "critical": Qgis.Critical}
            self.iface.messageBar().pushMessage("SIGMAI", text, level=levels.get(level, Qgis.Info), duration=5)
        except Exception:
            print(text)


SIGMAIPlugin = SIGMAIPlugin
