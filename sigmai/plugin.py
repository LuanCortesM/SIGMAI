"""Ponto de entrada do plugin SIGMAI no QGIS.

Esta classe faz três coisas: registra a ação no menu e na barra de ferramentas,
mantém a ponte local viva, e serve de *controlador* para o painel — o painel
não conhece o QGIS, só este objeto. A separação existe para que a interface
possa ser renderizada e testada com um controlador falso, fora de uma sessão
interativa do QGIS.
"""

from __future__ import annotations

#: A palavra de confirmação do Modo DEV. "SIM" para a interface em português,
#: "YES" para a interface em inglês — a caixa de diálogo mostra a da língua
#: ativa, e o código aceita as duas.
DEV_MODE_CONFIRMATION_WORDS = frozenset({"SIM", "YES"})

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge_server import SIGMAIServer
from .consent import DECISION_ALLOWED, DECISION_DENIED, MODE_ALLOW_SESSION, MODE_ASK, MODE_READ_ONLY, MODES
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

#: Opções renomeadas (nome antigo, nome novo). ``persist_token`` virou
#: ``persist_access_key`` na 1.1.4 porque o scanner de segurança do
#: repositório de plugins do QGIS (Bandit, regra B105) toma toda chave
#: terminada em ``_token`` com valor literal por senha embutida, e bloqueia a
#: versão. A migração preserva a escolha de quem tinha ligado a opção.
LEGACY_SETTING_NAMES = (("persist_token", "persist_access_key"),)


def migrate_legacy_settings(settings: Any, prefix: str = SETTINGS_PREFIX) -> None:
    """Copia cada opção de nome antigo para o novo e apaga a antiga.

    ``settings`` é um ``QgsSettings`` (ou qualquer objeto com ``contains``,
    ``value``, ``setValue`` e ``remove``). Se a opção nova já existe, vale ela.
    """
    for antiga, nova in LEGACY_SETTING_NAMES:
        chave_antiga = f"{prefix}/{antiga}"
        chave_nova = f"{prefix}/{nova}"
        if not settings.contains(chave_antiga):
            continue
        if not settings.contains(chave_nova):
            settings.setValue(chave_nova, settings.value(chave_antiga, False, type=bool))
        settings.remove(chave_antiga)

SETTINGS_DEFAULTS: dict[str, Any] = {
    "auto_start": True,
    "write_session_file": True,
    "persist_access_key": False,
    "consent_mode": MODE_READ_ONLY,
    "ui_language": "pt-BR",
    "ui_theme": "auto",
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
        self._migrate_legacy_settings()
        self.token = self._load_or_create_token()
        from .ui.strings import normalize_ui_language

        self.language = normalize_ui_language(self.settings_get("ui_language", "pt-BR"))
        self.theme_preference = str(self.settings_get("ui_theme", "auto") or "auto")
        self.server = SIGMAIServer(
            iface=iface,
            host=DEFAULT_HOST,
            port=DEFAULT_PORT,
            token=self.token,
            log_dir=self._log_dir(),
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

        self.panel = SigmaiPanel(self)
        self.apply_theme()

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

    # -- tema -------------------------------------------------------------
    def resolved_theme(self) -> str:
        """``"light"`` ou ``"dark"``: a preferência do usuário, ou a paleta do QGIS."""
        from .ui.theme import resolve_theme

        palette = None
        try:
            from qgis.PyQt.QtWidgets import QApplication  # type: ignore

            palette = QApplication.palette()
        except Exception:
            palette = None
        return resolve_theme(self.theme_preference, palette)

    def apply_theme(self) -> None:
        """Reaplica a folha de estilo no tema em vigor.

        Chamado ao criar o painel, quando o usuário muda a preferência em
        Avançado e quando o Qt anuncia troca de paleta (o painel ouve
        PaletteChange/StyleChange e chama de volta) — é assim que o painel
        acompanha "Night Mapping" ligado ou desligado com ele aberto.
        """
        if self.panel is None:
            return
        from .ui.theme import THEME_DARK, get_sigmai_stylesheet

        theme = self.resolved_theme()
        self.panel.apply_theme(theme, get_sigmai_stylesheet(self._ui_scale(), dark=(theme == THEME_DARK)))

    def set_theme(self, preference: str) -> None:
        from .ui.theme import THEME_PREFERENCES

        self.theme_preference = preference if preference in THEME_PREFERENCES else "auto"
        self.settings_set("ui_theme", self.theme_preference)
        self.apply_theme()

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
        invalidate_session_file(self.session_id)
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
        from .ui.strings import normalize_ui_language, translate

        self.language = normalize_ui_language(language)
        self.settings_set("ui_language", self.language)
        if self.dock is not None:
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
        if accepted and str(text).strip().upper() in DEV_MODE_CONFIRMATION_WORDS:
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
            results.append({"ok": False, "label": self._tr("selftest_bridge"), "detail": self._tr("selftest_bridge_off")})
            return results

        base = f"http://{self.server.host}:{self.server.port}"
        results.append(self._off_ui_thread(lambda: self._probe_health(base), self._tr("selftest_bridge"), 10))
        results.append(self._off_ui_thread(lambda: self._probe_auth(base), self._tr("selftest_auth"), 10))
        results.append(self._off_ui_thread(lambda: self._probe_command(base), self._tr("selftest_project"), 20))
        results.append(self._probe_session_file())
        results.append(self._off_ui_thread(self._probe_mcp_server, self._tr("selftest_mcp"), 30))
        results.append(self._probe_consent())
        return results

    def _off_ui_thread(self, probe: Any, label: str, timeout: float) -> dict[str, Any]:
        """Roda uma sonda numa thread e mantém o laço de eventos do Qt girando.

        O autoteste é chamado por um botão, na thread da interface. A sonda de
        projeto pede ``get_project_overview`` à ponte, e a ponte executa esse
        comando num QTimer DESSA MESMA thread: com a requisição feita ali, a
        interface ficava parada esperando a si mesma até o tempo esgotar —
        15 s de "Não respondendo" e um "timed out" falso no relatório.
        """
        box: dict[str, Any] = {}

        def worker() -> None:
            try:
                box["result"] = probe()
            except Exception as exc:  # noqa: BLE001 — vira linha do relatório
                box["result"] = {"ok": False, "label": label, "detail": str(exc)}

        thread = threading.Thread(target=worker, name="SIGMAISelfTest", daemon=True)
        thread.start()
        try:
            from qgis.PyQt.QtCore import QCoreApplication  # type: ignore

            pump = QCoreApplication.processEvents if QCoreApplication.instance() is not None else None
        except Exception:
            pump = None
        deadline = time.monotonic() + timeout
        while thread.is_alive() and time.monotonic() < deadline:
            if pump is not None:
                pump()
            thread.join(0.02)
        return box.get("result") or {"ok": False, "label": label, "detail": f"sem resposta em {timeout:g} s"}

    def _probe_health(self, base: str) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "label": self._tr("selftest_bridge"), "detail": self._tr("selftest_bridge_ok", host=self.server.host, port=self.server.port, version=payload.get("plugin_version"))}
        except Exception as exc:
            return {"ok": False, "label": self._tr("selftest_bridge"), "detail": self._tr("selftest_bridge_fail", error=exc)}

    def _probe_auth(self, base: str) -> dict[str, Any]:
        body = json.dumps({"action": "status"}).encode("utf-8")
        request = urllib.request.Request(base + "/command", data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(request, timeout=4)
            return {"ok": False, "label": self._tr("selftest_auth"), "detail": self._tr("selftest_auth_leak")}
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return {"ok": True, "label": self._tr("selftest_auth"), "detail": self._tr("selftest_auth_ok")}
            return {"ok": False, "label": self._tr("selftest_auth"), "detail": self._tr("selftest_auth_http", code=exc.code)}
        except Exception as exc:
            return {"ok": False, "label": self._tr("selftest_auth"), "detail": str(exc)}

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
                return {"ok": False, "label": self._tr("selftest_project"), "detail": str((payload.get("errors") or [{}])[0].get("message", ""))[:120]}
            data = payload.get("data") or {}
            return {
                "ok": True,
                "label": self._tr("selftest_project"),
                "detail": self._tr("selftest_project_ok", count=data.get("layer_count", 0), crs=data.get("project_crs") or self._tr("selftest_crs_undefined")),
            }
        except Exception as exc:
            return {"ok": False, "label": self._tr("selftest_project"), "detail": str(exc)}

    def _probe_session_file(self) -> dict[str, Any]:
        if not bool(self.settings_get("write_session_file", True)):
            return {"ok": False, "label": self._tr("selftest_session"), "detail": self._tr("selftest_session_disabled")}
        path = session_file_path()
        if not path.exists():
            return {"ok": False, "label": self._tr("selftest_session"), "detail": self._tr("selftest_session_missing", path=path)}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "label": self._tr("selftest_session"), "detail": self._tr("selftest_session_unreadable", error=exc)}
        if int(data.get("port", 0)) != int(self.server.port):
            return {"ok": False, "label": self._tr("selftest_session"), "detail": self._tr("selftest_session_port", file_port=data.get("port"), port=self.server.port)}
        return {"ok": True, "label": self._tr("selftest_session"), "detail": self._tr("selftest_session_ok")}

    def _probe_mcp_server(self) -> dict[str, Any]:
        server = Path(__file__).resolve().parent / "mcp" / "sigmai_mcp.py"
        if not server.exists():
            return {"ok": False, "label": self._tr("selftest_mcp"), "detail": self._tr("selftest_mcp_missing", path=server)}
        from .ui.client_configs import probe_mcp_server, python_executable

        executable = python_executable()
        if not Path(executable).exists() and executable not in {"python", "python3"}:
            return {"ok": False, "label": self._tr("selftest_mcp"), "detail": self._tr("selftest_mcp_no_python", executable=executable)}
        # O mesmo interpretador, o mesmo servidor e as mesmas variáveis do bloco
        # de configuração do passo 2 — senão o teste aprova o que o cliente
        # não consegue lançar.
        session = session_file_path() if bool(self.settings_get("write_session_file", True)) else None
        outcome = probe_mcp_server(executable, str(server), session_file=str(session) if session else None,
                                   expected_port=self.server.port)
        if not outcome["ok"]:
            return {"ok": False, "label": self._tr("selftest_mcp"),
                    "detail": self._tr("selftest_mcp_failed", python=executable, stage=outcome["stage"], error=outcome["error"])}
        return {"ok": True, "label": self._tr("selftest_mcp"), "detail": self._tr("selftest_mcp_ok", server=server.name, python=executable)}

    def _probe_consent(self) -> dict[str, Any]:
        status = self.consent.status()
        if status["mode"] == MODE_READ_ONLY:
            return {"ok": False, "label": self._tr("selftest_mode"), "detail": self._tr("selftest_mode_read_only")}
        mode_key = {MODE_ASK: "mode_ask", MODE_ALLOW_SESSION: "mode_allow"}.get(status["mode"], "mode_read_only")
        return {"ok": True, "label": self._tr("selftest_mode"), "detail": self._tr(mode_key)}

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
        box.setText(f"<b>{self._category_name(request)}</b> — {self._category_description(request)}")
        box.setInformativeText(self._describe_request(request))
        remember = QCheckBox(translate(self.language, "consent_allow_category"))
        box.setCheckBox(remember)
        allow = box.addButton(translate(self.language, "consent_allow"), qt_enum(QMessageBox, "ButtonRole", "AcceptRole"))
        box.addButton(translate(self.language, "consent_deny"), qt_enum(QMessageBox, "ButtonRole", "RejectRole"))
        box.exec() if hasattr(box, "exec") else box.exec_()
        allowed = box.clickedButton() is allow
        self._refresh_panel()
        return (DECISION_ALLOWED if allowed else DECISION_DENIED, bool(remember.isChecked()))

    def _category_name(self, request: Any) -> str:
        """Nome da categoria na língua da interface.

        O registro de consentimento guarda o nome canônico em português
        ("Cartografia") — é ele que "lembrar esta categoria" compara —, por
        isso a tradução é só de exibição, feita aqui e não em consent.py.
        """
        from .consent import CATEGORY_KEYS

        key = CATEGORY_KEYS.get(request.category)
        return self._tr(key) if key else str(request.category)

    def _category_description(self, request: Any) -> str:
        from .consent import ACTION_CATEGORIES

        key = f"category_desc_{request.group}" if request.group in ACTION_CATEGORIES else "category_desc_default"
        # vector_tools e vector_analysis (e symbology/labels, workflows/job_queue)
        # compartilham a descrição; a chave existe só para o primeiro de cada par.
        aliases = {"category_desc_vector_tools": "category_desc_vector", "category_desc_vector_analysis": "category_desc_vector",
                   "category_desc_labels": "category_desc_symbology", "category_desc_job_queue": "category_desc_workflows"}
        return self._tr(aliases.get(key, key))

    def _describe_request(self, request: Any) -> str:
        outputs = request.output_paths()
        parts = [f"{self._tr('consent_action')}: {request.action}", f"{self._tr('consent_category')}: {self._category_name(request)}"]
        if outputs:
            parts.append(f"{self._tr('consent_writes_to')}: " + "; ".join(outputs))
        interesting = {
            key: value for key, value in request.params.items()
            if key in {"layout_name", "layer_id", "layer_ids", "title", "page", "template", "format", "algorithm_id"}
        }
        if interesting:
            parts.append(f"{self._tr('consent_params')}: " + json.dumps(interesting, ensure_ascii=False)[:300])
        return "\n".join(parts)

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
        """Token novo a cada abertura do QGIS, a menos que o usuário peça o contrário.

        A configuração do cliente (passo 2) não contém o token: o servidor MCP
        o relê do arquivo de sessão a cada chamada. Regenerar não obriga a
        refazer nada e tranca para fora quem guardou o token de uma sessão
        anterior — o que SECURITY_MODEL.md promete. Até a 1.1.2 o padrão era
        manter, com a justificativa (já falsa) de que o cliente precisava ser
        reconfigurado. Quem colou o token à mão em algum lugar liga a opção.
        """
        if not bool(self.settings_get("persist_access_key", False)):
            # Um token guardado por uma versão anterior não fica esquecido nas
            # configurações do perfil.
            if self.settings_get("bridge_token", ""):
                self.settings_set("bridge_token", "")
            return generate_token()
        stored = str(self.settings_get("bridge_token", "") or "")
        if len(stored) >= 32:
            return stored
        token = generate_token()
        self._store_token(token)
        return token

    def _migrate_legacy_settings(self) -> None:
        try:
            from qgis.core import QgsSettings  # type: ignore

            migrate_legacy_settings(QgsSettings())
        except Exception:
            pass

    def _store_token(self, token: str) -> None:
        if bool(self.settings_get("persist_access_key", False)):
            self.settings_set("bridge_token", token)

    # -- auxiliares -------------------------------------------------------
    @staticmethod
    def _log_dir() -> Path:
        """Os logs vão para o perfil do QGIS, não para a pasta do plugin.

        Gravar dentro da pasta de instalação parecia funcionar até aparecer um
        sigmai.jsonl de 29 KB versionado por engano na árvore-fonte — e numa
        instalação de sistema, com a pasta de plugins somente-leitura, a
        primeira gravação falha. O perfil do usuário é gravável por definição.
        """
        try:
            from qgis.core import QgsApplication  # type: ignore

            base = Path(QgsApplication.qgisSettingsDirPath()) / "sigmai" / "logs"
        except Exception:
            base = Path.home() / ".local" / "share" / "sigmai" / "logs"
        try:
            base.mkdir(parents=True, exist_ok=True)
            return base
        except OSError:
            return Path(__file__).resolve().parent / "logs"

    def plugin_version(self) -> str:
        # Um único leitor de metadata.txt para todo o pacote: a lógica estava
        # copiada em três lugares, e o docstring do primeiro contava a história
        # de como isso já produziu uma versão publicada divergente.
        from .bridge_server import plugin_version

        return plugin_version()
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
