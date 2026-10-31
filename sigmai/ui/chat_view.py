"""O chat dentro do painel do SIGMAI: conversa com um modelo que só tem as ferramentas do SIGMAI.

É uma página do próprio painel, e não uma janela à parte: o botão "API e
Chat" do cabeçalho troca as abas por esta página, com a mesma folha de estilo
(``ui/theme.py``). Na primeira vez aparece o cartão "Conecte sua IA"; depois,
só a conversa, e a configuração fica atrás de um botão.

A conversa roda numa thread de trabalho (``_Worker``), para o QGIS não travar
enquanto o provedor responde; as ferramentas vão à ponte local pelo mesmo
caminho de um cliente MCP externo (``sigmai_mcp.run_tool``). A prévia do mapa
é desenhada na thread principal, que é onde o QGIS desenha layouts, e volta à
thread de trabalho por uma conexão bloqueante.

O ``controller`` é o plugin: ``language``, ``server``, ``token``,
``start_bridge()``, ``settings_get/set`` e ``log_dir()``.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

from ..cartography.qtcompat import qt_enum
from .strings import translate

try:  # pragma: no cover - só falha fora do QGIS
    from qgis.PyQt.QtCore import QBuffer, QByteArray, QObject, QSize, Qt, QThread, QTimer, pyqtSignal, pyqtSlot  # type: ignore
    from qgis.PyQt.QtWidgets import (  # type: ignore
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except Exception as exc:  # pragma: no cover
    raise ImportError("O chat do SIGMAI exige PyQt do QGIS.") from exc

BLOCKING = qt_enum(Qt, "ConnectionType", "BlockingQueuedConnection")
ECHO_PASSWORD = qt_enum(QLineEdit, "EchoMode", "Password")
MARKDOWN = qt_enum(Qt, "TextFormat", "MarkdownText")
PLAIN = qt_enum(Qt, "TextFormat", "PlainText")
SELECTABLE = qt_enum(Qt, "TextInteractionFlag", "TextSelectableByMouse")
NO_FRAME = qt_enum(QFrame, "Shape", "NoFrame")
EXPANDING = qt_enum(QSizePolicy, "Policy", "Expanding")
PREFERRED = qt_enum(QSizePolicy, "Policy", "Preferred")
ALWAYS_OFF = qt_enum(Qt, "ScrollBarPolicy", "ScrollBarAlwaysOff")
SHRINKABLE = qt_enum(QComboBox, "SizeAdjustPolicy", "AdjustToMinimumContentsLengthWithIcon")
PREVIEW_MAX_PX = 1000


class _PreviewRenderer(QObject):
    """Desenha o layout em PNG pequeno, na thread principal."""

    def __init__(self) -> None:
        super().__init__()
        self.result: bytes | None = None

    @pyqtSlot(str)
    def render(self, layout_name: str) -> None:
        self.result = None
        try:
            from qgis.core import QgsLayoutExporter, QgsProject  # type: ignore

            layout = QgsProject.instance().layoutManager().layoutByName(layout_name)
            if layout is None or layout.pageCollection().pageCount() == 0:
                return
            width_mm = layout.pageCollection().page(0).pageSize().width()
            dpi = max(30.0, min(150.0, PREVIEW_MAX_PX / (width_mm / 25.4))) if width_mm > 0 else 72.0
            image = QgsLayoutExporter(layout).renderPageToImage(0, QSize(), dpi)
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(qt_enum(QBuffer, "OpenModeFlag", "WriteOnly"))
            image.save(buffer, "PNG")
            self.result = bytes(data)
        except Exception:
            self.result = None


class _Worker(QObject):
    # Não pode se chamar "event": esconderia QObject.event(), por onde o Qt
    # entrega a chamada enfileirada à thread de trabalho.
    progress = pyqtSignal(str, object)
    finished = pyqtSignal(object)
    wants_preview = pyqtSignal(str)

    def __init__(self, renderer: _PreviewRenderer) -> None:
        super().__init__()
        self.session: Any = None
        self.renderer = renderer
        self.stop_requested = False

    def preview(self, tool_name: str, payload: Any) -> bytes | None:
        data = payload.get("data") if isinstance(payload, dict) else None
        name = data.get("layout_name") if isinstance(data, dict) else None
        if not name or (isinstance(data, dict) and data.get("dry_run")):
            return None
        self.wants_preview.emit(str(name))
        return self.renderer.result

    @pyqtSlot(str)
    def run(self, text: str) -> None:
        self.stop_requested = False
        try:
            result = self.session.send(text, lambda kind, payload: self.progress.emit(kind, payload),
                                       lambda: self.stop_requested)
        except Exception as exc:  # o laço nunca derruba o painel
            self.progress.emit("error", exc)
            result = None
        self.finished.emit(result)


def _label(text: str, name: str, markdown: bool = False) -> QLabel:
    label = QLabel()
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextFormat(MARKDOWN if markdown else PLAIN)
    label.setTextInteractionFlags(SELECTABLE)
    label.setText(text)
    return label


class ChatView(QWidget):
    request_send = pyqtSignal(str)

    def __init__(self, controller: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatPage")
        self.controller = controller
        self.session: Any = None
        self.entries: list[list[str]] = []
        self.busy = False
        self.script: list[str] = self._load_script()
        self.script_log: dict[str, Any] = {}
        self._current: QLabel | None = None
        self._current_text = ""
        self._note: QLabel | None = None
        self._tool: QLabel | None = None
        self._build()
        self._renderer = _PreviewRenderer()
        self._thread = QThread(self)
        self._worker = _Worker(self._renderer)
        self._worker.moveToThread(self._thread)
        self._worker.progress.connect(self._on_event)
        self._worker.finished.connect(self._on_finished)
        self._worker.wants_preview.connect(self._renderer.render, BLOCKING)
        self.request_send.connect(self._worker.run)
        self._thread.start()
        self._flush = QTimer(self)
        self._flush.setSingleShot(True)
        self._flush.timeout.connect(self._flush_text)
        self.refresh()
        if self.script and os.environ.get("SIGMAI_CHAT_AUTORUN") == "1":
            delay = os.environ.get("SIGMAI_CHAT_AUTORUN_DELAY_MS", "1500")
            QTimer.singleShot(int(delay) if delay.isdigit() else 1500, self._run_script)

    # -- textos e ajustes -------------------------------------------------------
    def tr_(self, key: str, **kwargs: Any) -> str:
        return translate(getattr(self.controller, "language", "pt-BR"), key, **kwargs)

    def _setting(self, key: str, default: Any) -> Any:
        return self.controller.settings_get(f"chat_{key}", default)

    def _set(self, key: str, value: Any) -> None:
        self.controller.settings_set(f"chat_{key}", value)

    def _provider(self) -> str:
        return str(self.provider_combo.currentData() or "anthropic")

    # -- montagem ---------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(self._build_setup())
        outer.addWidget(self._build_status())
        outer.addWidget(self._build_messages(), 1)
        self.input_card = self._build_input()
        outer.addWidget(self.input_card)
        # Com o cartão de configuração aberto, ele é a página inteira: a
        # conversa espremida embaixo dele não servia para nada.
        self.setup_spacer = QWidget()
        self.setup_spacer.setObjectName("transparentRow")
        outer.addWidget(self.setup_spacer, 1)

    def _build_setup(self) -> QFrame:
        """Cartão "Conecte sua IA": provedor, modelo, chave e o que vai para o provedor."""
        from ..chat.providers import ANTHROPIC_MODELS, OPENAI_PRESETS

        self.setup_card = QFrame()
        self.setup_card.setObjectName("stepCardActive")
        layout = QVBoxLayout(self.setup_card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        self.setup_title = _label(self.tr_("chat_setup_title"), "stepTitle")
        self.setup_hint = _label(self.tr_("chat_setup_hint"), "stepHint")
        layout.addWidget(self.setup_title)
        layout.addWidget(self.setup_hint)

        form = QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Anthropic (Claude)", "anthropic")
        self.provider_combo.addItem(self.tr_("chat_provider_openai"), "openai_compatible")
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.base_url_combo = QComboBox()
        self.base_url_combo.setEditable(True)
        for name, url in OPENAI_PRESETS.items():
            self.base_url_combo.addItem(url, name)
        self.effort_combo = QComboBox()
        for value in ("low", "medium", "high"):
            self.effort_combo.addItem(self.tr_(f"chat_effort_{value}"), value)
        # Sem isto a lista mede-se pelo item mais longo (a URL do Gemini) e
        # alarga o painel inteiro além do dock.
        for combo in (self.provider_combo, self.model_combo, self.base_url_combo, self.effort_combo):
            combo.setSizeAdjustPolicy(SHRINKABLE)
            combo.setMinimumContentsLength(10)
        key_row = QWidget()
        key_row.setObjectName("transparentRow")
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(6)
        self.key_field = QLineEdit()
        self.key_field.setObjectName("codeField")
        self.key_field.setEchoMode(ECHO_PASSWORD)
        self.key_save = QPushButton(self.tr_("chat_key_save"))
        self.key_save.setObjectName("primaryButton")
        key_layout.addWidget(self.key_field, 1)
        key_layout.addWidget(self.key_save)
        self.key_state = _label("", "helpText")
        self.preview_check = QCheckBox(self.tr_("chat_preview"))
        self.preview_check.setToolTip(self.tr_("chat_preview_hint"))
        self.cap_spin = QDoubleSpinBox()
        self.cap_spin.setRange(0.0, 1000.0)
        self.cap_spin.setDecimals(2)
        self.cap_spin.setPrefix("US$ ")
        self.cap_spin.setButtonSymbols(qt_enum(QDoubleSpinBox, "ButtonSymbols", "NoButtons"))
        self.cap_spin.setToolTip(self.tr_("chat_cap_hint"))
        self.form_labels = {}
        for key, widget in (("chat_provider_label", self.provider_combo), ("chat_model_label", self.model_combo),
                            ("chat_base_url_label", self.base_url_combo), ("chat_effort", self.effort_combo),
                            ("chat_key_label", key_row), ("", self.key_state), ("", self.preview_check),
                            ("chat_cap", self.cap_spin)):
            label = QLabel(self.tr_(key) if key else "")
            if key:
                self.form_labels[key] = label
            form.addRow(label, widget)
        layout.addLayout(form)
        self.privacy_label = _label(self.tr_("chat_privacy_text"), "noticeWarn")
        layout.addWidget(self.privacy_label)
        done_row = QHBoxLayout()
        done_row.addStretch(1)
        self.setup_done = QPushButton(self.tr_("chat_setup_done"))
        done_row.addWidget(self.setup_done)
        layout.addLayout(done_row)

        provider = str(self._setting("provider", "anthropic"))
        self.provider_combo.setCurrentIndex(max(0, self.provider_combo.findData(provider)))
        self._fill_models(ANTHROPIC_MODELS)
        self.effort_combo.setCurrentIndex(max(0, self.effort_combo.findData(str(self._setting("effort", "medium")))))
        self.base_url_combo.setCurrentText(str(self._setting("base_url", OPENAI_PRESETS["openai"])))
        self.preview_check.setChecked(bool(self._setting("preview", True)))
        self.cap_spin.setValue(float(self._setting("cost_cap", 5.0)))
        # O modo de teste pode subir o teto: uma sessão roteirizada longa não
        # deve parar no meio por causa do padrão pensado para o uso comum.
        cap = os.environ.get("SIGMAI_CHAT_COST_CAP", "") if self.script else ""
        if cap.replace(".", "", 1).isdigit():
            self.cap_spin.setValue(float(cap))

        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self.model_combo.currentTextChanged.connect(lambda text: self._settings_changed())
        self.effort_combo.currentIndexChanged.connect(lambda index: self._settings_changed())
        self.base_url_combo.currentTextChanged.connect(self._base_url_changed)
        self.preview_check.toggled.connect(lambda checked: self._settings_changed())
        self.cap_spin.valueChanged.connect(self._cap_changed)
        self.key_save.clicked.connect(self._save_key)
        self.key_field.returnPressed.connect(self._save_key)
        self.setup_done.clicked.connect(lambda: self._show_setup(False))
        return self.setup_card

    def _build_status(self) -> QWidget:
        """Faixa fina quando a IA já está conectada: modelo e o botão de configurar."""
        self.status_row = QWidget()
        self.status_row.setObjectName("transparentRow")
        row = QHBoxLayout(self.status_row)
        row.setContentsMargins(0, 0, 0, 0)
        # A etiqueta do modelo é o próprio botão de configurar: dois links lado
        # a lado não cabiam no dock estreito em francês e italiano.
        self.status_pill = QPushButton()
        self.status_pill.setObjectName("chatStatusButton")
        self.status_pill.setToolTip(self.tr_("chat_configure"))
        self.configure_button = self.status_pill
        self.new_button = QPushButton(self.tr_("chat_new"))
        self.new_button.setObjectName("linkButton")
        row.addWidget(self.status_pill)
        row.addStretch(1)
        row.addWidget(self.new_button)
        self.configure_button.clicked.connect(lambda: self._show_setup(True))
        self.new_button.clicked.connect(self._new_conversation)
        return self.status_row

    def _build_messages(self) -> QScrollArea:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(NO_FRAME)
        self.scroll.setHorizontalScrollBarPolicy(ALWAYS_OFF)
        holder = QWidget()
        holder.setObjectName("chatMessages")
        self.messages = QVBoxLayout(holder)
        self.messages.setContentsMargins(2, 2, 6, 2)
        self.messages.setSpacing(8)
        self.empty_label = _label(self.tr_("chat_intro"), "helpText")
        self.messages.addWidget(self.empty_label)
        self.messages.addStretch(1)
        self.scroll.setWidget(holder)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._stick_to_bottom)
        self._at_bottom = True
        self.scroll.verticalScrollBar().valueChanged.connect(
            lambda value: setattr(self, "_at_bottom", value >= self.scroll.verticalScrollBar().maximum() - 4))
        return self.scroll

    def _build_input(self) -> QFrame:
        card = QFrame()
        card.setObjectName("stepCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        self.input = QPlainTextEdit()
        self.input.setObjectName("chatInput")
        self.input.setPlaceholderText(self.tr_("chat_placeholder"))
        self.input.setFixedHeight(76)
        layout.addWidget(self.input)
        row = QHBoxLayout()
        self.cost_label = _label("", "chatCost")
        self.export_button = QPushButton(self.tr_("chat_export"))
        self.export_button.setObjectName("linkButton")
        self.export_button.setToolTip(self.tr_("chat_export_hint"))
        self.continue_button = QPushButton(self.tr_("chat_continue_cap"))
        self.continue_button.setVisible(False)
        self.stop_button = QPushButton(self.tr_("chat_stop"))
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setVisible(False)
        self.send_button = QPushButton(self.tr_("chat_send"))
        self.send_button.setObjectName("primaryButton")
        row.addWidget(self.cost_label, 1)
        row.addWidget(self.export_button)
        row.addWidget(self.continue_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        self.send_button.clicked.connect(self._send_clicked)
        self.stop_button.clicked.connect(self._stop)
        self.continue_button.clicked.connect(self._continue_over_cap)
        self.export_button.clicked.connect(self._export)
        return card

    # -- estado ---------------------------------------------------------------------
    def refresh(self) -> None:
        """Mostra o cartão de configuração enquanto não houver chave (ou modelo)."""
        from ..chat.keys import load_key

        key, origin = load_key(self._provider())
        ready = bool(key) or self._provider() == "openai_compatible"
        if key:
            self.key_state.setText(self.tr_("chat_key_ok", origin=self.tr_(f"chat_key_origin_{_origin_key(origin)}")))
        else:
            self.key_state.setText(self.tr_("chat_key_missing"))
        self.key_field.setPlaceholderText(self.tr_("chat_key_placeholder_saved") if key else self.tr_("chat_key_placeholder"))
        self.status_pill.setText(self._status_text())
        self._show_setup(not ready or self.setup_card.isVisible() and getattr(self, "_setup_forced", False))
        self._sync_provider_widgets()

    def _show_setup(self, visible: bool) -> None:
        self._setup_forced = visible
        self.setup_card.setVisible(visible)
        self.setup_spacer.setVisible(visible)
        self.status_row.setVisible(not visible)
        self.scroll.setVisible(not visible)
        self.input_card.setVisible(not visible)
        if not visible:
            self.status_pill.setText(self._status_text())

    def _fill_models(self, anthropic_models: tuple[str, ...]) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        anthropic = self._provider() == "anthropic"
        self.model_combo.setEditable(not anthropic)
        if anthropic:
            for model in anthropic_models:
                self.model_combo.addItem(MODEL_NAMES.get(model, model), model)
            saved = str(self._setting("model", "claude-opus-5-5"))
            self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(saved)))
        else:
            self.model_combo.setCurrentText(str(self._setting("openai_model", "")))
            self.model_combo.lineEdit().setPlaceholderText(self.tr_("chat_model_placeholder"))
        self.model_combo.blockSignals(False)

    def _model_id(self) -> str:
        if self._provider() == "anthropic":
            return str(self.model_combo.currentData() or "claude-opus-5-5")
        return self.model_combo.currentText().strip()

    def _status_text(self) -> str:
        if self._provider() == "anthropic":
            short = self.model_combo.currentText().replace("Claude ", "")
            return f"●  {short}  ·  {self.effort_combo.currentText()}   ⚙"
        return f"●  {self._model_id() or '—'}   ⚙" 

    def _sync_provider_widgets(self) -> None:
        anthropic = self._provider() == "anthropic"
        for key, widget in (("chat_effort", self.effort_combo), ("chat_base_url_label", self.base_url_combo)):
            show = anthropic if key == "chat_effort" else not anthropic
            widget.setVisible(show)
            self.form_labels[key].setVisible(show)

    def _provider_changed(self, index: int) -> None:
        from ..chat.providers import ANTHROPIC_MODELS

        self._set("provider", self._provider())
        self._fill_models(ANTHROPIC_MODELS)
        self._settings_changed()
        self.refresh()

    def _settings_changed(self) -> None:
        if self._provider() == "anthropic":
            self._set("model", self._model_id())
            self._set("effort", str(self.effort_combo.currentData() or "medium"))
        else:
            self._set("openai_model", self.model_combo.currentText().strip())
            self._set("base_url", self.base_url_combo.currentText().strip())
        self._set("preview", self.preview_check.isChecked())
        self.status_pill.setText(self._status_text())
        # Trocar provedor ou modelo começa conversa nova: cada provedor guarda o
        # histórico no formato dele, e o raciocínio de um modelo não vale noutro.
        if self.session is not None and not self.busy:
            self.session = None
            self._add_notice(self.tr_("chat_new_after_settings"))

    def _base_url_changed(self, text: str) -> None:
        from ..chat.providers import PRESET_MODELS

        preset = self.base_url_combo.currentData() if self.base_url_combo.currentText() == self.base_url_combo.itemText(
            self.base_url_combo.currentIndex()) else None
        if self._provider() == "openai_compatible" and preset in PRESET_MODELS and not self.model_combo.currentText().strip():
            self.model_combo.setCurrentText(PRESET_MODELS[preset])
        self._settings_changed()

    def _cap_changed(self, value: float) -> None:
        self._set("cost_cap", float(value))
        if self.session is not None:
            self.session.cost_cap_usd = float(value) or None

    def _save_key(self) -> None:
        from ..chat.keys import remove_key, save_key

        text = self.key_field.text().strip()
        self.key_field.clear()
        if text:
            save_key(self._provider(), text)
        else:
            remove_key(self._provider())
        self.session = None
        self.refresh()
        if getattr(self, "_script_waiting", False) and text:
            self._show_setup(False)
            QTimer.singleShot(500, self._run_script)

    # -- conversa -------------------------------------------------------------------
    def _make_session(self) -> Any:
        from ..chat.keys import load_key
        from ..chat.providers import ANTHROPIC_URL, AnthropicProvider, OpenAICompatibleProvider, ProviderError
        from ..chat.qgis_transport import qgis_transport
        from ..chat.session import ChatSession, system_prompt
        from ..mcp import sigmai_mcp

        key, _origin = load_key(self._provider())
        model = self._model_id()
        if self._provider() == "anthropic":
            if not key:
                raise ProviderError("auth", self.tr_("chat_key_missing_long"))
            # Servidor falso local para os testes de ponta a ponta; check_url
            # recusa qualquer endereço http que não seja desta máquina.
            test_url = os.environ.get("SIGMAI_CHAT_TEST_URL", "")
            provider: Any = AnthropicProvider(key, model=model or "claude-opus-5-5",
                                              effort=str(self.effort_combo.currentData() or "medium"), transport=qgis_transport,
                                              url=test_url if test_url.startswith("http://127.0.0.1") else ANTHROPIC_URL)
        else:
            if not model:
                raise ProviderError("bad_request", self.tr_("chat_model_missing"))
            provider = OpenAICompatibleProvider(key, self.base_url_combo.currentText().strip(), model, transport=qgis_transport,
                                                send_images=self.preview_check.isChecked())
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = Path(self.controller.log_dir()) / "chat" / f"{stamp}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        system = system_prompt(sigmai_mcp.INSTRUCTIONS, scripted=bool(self.script), preview=self.preview_check.isChecked())
        return ChatSession(provider, sigmai_mcp.run_tool, sigmai_mcp._tool_manifest(), system,
                           cost_cap_usd=float(self.cap_spin.value()) or None,
                           preview=self._worker.preview if self.preview_check.isChecked() else None,
                           log_path=log_path)

    def _prepare_bridge(self) -> None:
        from ..mcp import sigmai_mcp

        server = self.controller.server
        if not getattr(server, "running", False):
            self.controller.start_bridge()
        sigmai_mcp.CONNECTION_OVERRIDES.update({"host": server.host, "port": server.port, "token": self.controller.token})

    def _send_clicked(self) -> None:
        text = self.input.toPlainText().strip()
        if text and self._send(text):
            self.input.clear()

    def _send(self, text: str) -> bool:
        if self.busy:
            return False
        try:
            self._prepare_bridge()
            if self.session is None:
                self.session = self._make_session()
        except Exception as exc:
            self._add_bubble("error", str(exc))
            return False
        self._worker.session = self.session
        self._add_bubble("user", text)
        self._set_busy(True)
        self.request_send.emit(text)
        return True

    def _stop(self) -> None:
        self._worker.stop_requested = True
        self.stop_button.setEnabled(False)

    def _continue_over_cap(self) -> None:
        if self.session is not None:
            self.session.over_cap_allowed = True
        self.continue_button.setVisible(False)
        self._send(self.tr_("chat_continue_message"))

    def _new_conversation(self) -> None:
        if self.busy:
            return
        self.session = None
        self.entries.clear()
        while self.messages.count() > 1:
            item = self.messages.takeAt(0)
            if item.widget() is not None and item.widget() is not self.empty_label:
                item.widget().deleteLater()
        self.messages.insertWidget(0, self.empty_label)
        self.empty_label.setVisible(True)
        self.cost_label.setText("")

    def _export(self) -> None:
        if not self.entries:
            return
        path, _filter = QFileDialog.getSaveFileName(self, self.tr_("chat_export"), "conversa_sigmai.md", "Markdown (*.md)")
        if path:
            Path(path).write_text(self._markdown(), encoding="utf-8")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.send_button.setVisible(not busy)
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(busy)
        self.configure_button.setEnabled(not busy)
        self.new_button.setEnabled(not busy)

    # -- balões ---------------------------------------------------------------------
    def _append(self, widget: QWidget, align: str = "left") -> None:
        self.empty_label.setVisible(False)
        row = QWidget()
        row.setObjectName("transparentRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        if align == "right":
            layout.addStretch(1)
            layout.addWidget(widget, 6)
        elif align == "full":
            layout.addWidget(widget, 1)
        else:
            layout.addWidget(widget, 6)
            layout.addStretch(1)
        self.messages.insertWidget(self.messages.count() - 1, row)

    def _add_bubble(self, kind: str, text: str) -> QLabel:
        self.entries.append([kind, text])
        if kind in ("user", "assistant"):
            bubble = QFrame()
            bubble.setObjectName("chatBubbleUser" if kind == "user" else "chatBubbleAssistant")
            bubble.setSizePolicy(PREFERRED, PREFERRED)
            layout = QVBoxLayout(bubble)
            layout.setContentsMargins(12, 8, 12, 10)
            layout.setSpacing(2)
            who = _label(self.tr_("chat_you") if kind == "user" else "SIGMAI", "chatWho")
            body = _label(text, "chatText", markdown=(kind == "assistant"))
            layout.addWidget(who)
            layout.addWidget(body)
            self._append(bubble, "right" if kind == "user" else "left")
            return body
        name = {"tool": "chatTool", "note": "chatNote", "error": "noticeDanger", "notice": "helpText"}.get(kind, "helpText")
        label = _label(text, name)
        self._append(label, "full" if kind in ("error", "notice") else "left")
        return label

    def _add_notice(self, text: str) -> None:
        self._add_bubble("notice", text)

    def _stick_to_bottom(self, minimum: int, maximum: int) -> None:
        if self._at_bottom:
            self.scroll.verticalScrollBar().setValue(maximum)

    # -- eventos da thread de trabalho ------------------------------------------
    def _on_event(self, kind: str, payload: Any) -> None:
        if kind == "text":
            if self._current is None:
                self._current = self._add_bubble("assistant", "")
                self._current_index = len(self.entries) - 1
                self._current_text = ""
            self._current_text += str(payload)
            self.entries[self._current_index][1] = self._current_text
            if not self._flush.isActive():
                self._flush.start(100)
            self._note = None
        elif kind == "note":
            if self._note is None:
                self._flush_text()
                self._current = None
                self._note = self._add_bubble("note", "")
            self._note.setText((self._note.text() + str(payload)).strip())
        elif kind == "tool_start":
            self._flush_text()
            self._current = self._note = None
            self._tool = self._add_bubble("tool", f"…  {payload.get('name')}")
        elif kind == "tool_end":
            mark = "✗" if payload.get("error") else "✓"
            line = f"{mark}  {payload.get('name')}" + (f"  ·  {payload.get('summary')}" if payload.get("summary") else "")
            if self._tool is not None:
                self._tool.setText(line)
                if self.entries and self.entries[-1][0] == "tool":
                    self.entries[-1][1] = line
            else:
                self._add_bubble("tool", line)
            self._tool = None
        elif kind == "preview":
            self._add_bubble("tool", "•  " + self.tr_("chat_preview_sent"))
        elif kind == "usage":
            self._show_usage(payload)
        elif kind == "error":
            self._add_bubble("error", self._error_text(payload))
        elif kind == "refusal":
            self._add_bubble("error", self.tr_("chat_refusal"))
        elif kind == "cap":
            self._add_bubble("error", self.tr_("chat_cap_reached", cost=f"{float(payload):.2f}"))
            self.continue_button.setVisible(True)
        elif kind == "notice":
            self._add_notice(str(payload))
        elif kind == "stopped":
            self._add_notice(self.tr_("chat_stopped"))
        elif kind == "retry":
            self._add_notice(self.tr_("chat_retry", seconds=int(payload.get("seconds", 0))))
        elif kind == "fallback":
            self._add_notice(self.tr_("chat_model_fallback", old=payload.get("from"), new=payload.get("to")))

    def _flush_text(self) -> None:
        if self._current is not None:
            self._current.setText(self._current_text)

    def _on_finished(self, result: Any) -> None:
        self._flush_text()
        self._current = self._note = self._tool = None
        self._set_busy(False)
        if self.script:
            self._script_step(result)

    def _error_text(self, error: Any) -> str:
        kind = getattr(error, "kind", "")
        known = {"auth": "chat_error_auth", "rate_limit": "chat_error_rate", "overloaded": "chat_error_overloaded",
                 "network": "chat_error_network", "timeout": "chat_error_timeout"}
        if kind == "cancelled":
            return self.tr_("chat_stopped")
        if kind in known:
            return self.tr_(known[kind]) + f"\n{error}"
        return str(error)

    def _show_usage(self, payload: dict[str, Any]) -> None:
        from ..chat.pricing import PRICES_DATE

        usage = payload.get("usage")
        cost = payload.get("cost")
        total = usage.input + usage.cache_write + usage.cache_read + usage.output
        language = getattr(self.controller, "language", "pt-BR")
        detail = self.tr_("chat_usage", input=_number(usage.input + usage.cache_write, language),
                          cache=_number(usage.cache_read, language), output=_number(usage.output, language))
        visible = f"{_number(round(total / 1000), language)}k tokens"
        if cost is not None:
            money = _money(cost, language)
            visible = f"≈ US$ {money}  ·  {visible}"
            detail += "\n" + self.tr_("chat_cost", cost=money, date=PRICES_DATE)
        self.cost_label.setText(visible)
        self.cost_label.setToolTip(detail)

    def _markdown(self) -> str:
        parts = []
        for kind, text in self.entries:
            if not text:
                continue
            if kind == "user":
                parts.append(f"**{self.tr_('chat_you')}:** {text}")
            elif kind == "assistant":
                parts.append(text)
            elif kind == "tool":
                parts.append(f"> `{text}`")
            elif kind == "note":
                parts.append("> _" + " ".join(text.split()) + "_")
            elif kind == "error":
                parts.append(f"**{self.tr_('chat_error')}:** {text}")
            else:
                parts.append(f"_{text}_")
        return "\n\n".join(parts)

    def retranslate(self) -> None:
        self.setup_title.setText(self.tr_("chat_setup_title"))
        self.setup_hint.setText(self.tr_("chat_setup_hint"))
        for key, label in self.form_labels.items():
            label.setText(self.tr_(key))
        self.provider_combo.setItemText(1, self.tr_("chat_provider_openai"))
        for index in range(self.effort_combo.count()):
            self.effort_combo.setItemText(index, self.tr_(f"chat_effort_{self.effort_combo.itemData(index)}"))
        self.key_save.setText(self.tr_("chat_key_save"))
        self.preview_check.setText(self.tr_("chat_preview"))
        self.preview_check.setToolTip(self.tr_("chat_preview_hint"))
        self.cap_spin.setToolTip(self.tr_("chat_cap_hint"))
        self.privacy_label.setText(self.tr_("chat_privacy_text"))
        self.setup_done.setText(self.tr_("chat_setup_done"))
        self.configure_button.setToolTip(self.tr_("chat_configure"))
        self.new_button.setText(self.tr_("chat_new"))
        self.empty_label.setText(self.tr_("chat_intro"))
        self.input.setPlaceholderText(self.tr_("chat_placeholder"))
        self.export_button.setText(self.tr_("chat_export"))
        self.export_button.setToolTip(self.tr_("chat_export_hint"))
        self.continue_button.setText(self.tr_("chat_continue_cap"))
        self.stop_button.setText(self.tr_("chat_stop"))
        self.send_button.setText(self.tr_("chat_send"))
        self.refresh()

    # -- roteiro de teste (exemplo do artigo) -------------------------------------
    @staticmethod
    def _load_script() -> list[str]:
        path = os.environ.get("SIGMAI_CHAT_SCRIPT", "")
        if not path:
            return []
        try:
            messages = json.loads(Path(path).read_text(encoding="utf-8"))
            return [str(message) for message in messages] if isinstance(messages, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _run_script(self) -> None:
        from ..chat.keys import load_key
        from ..chat.providers import _is_loopback

        # Sem chave, o roteiro espera a pessoa colá-la no cartão e salvar:
        # quem roda o exemplo é ela, com a chave dela. Um modelo local
        # (Ollama, nesta máquina) não precisa de chave.
        local = self._provider() == "openai_compatible" and _is_loopback(self.base_url_combo.currentText())
        if not local and not load_key(self._provider())[0]:
            self._script_waiting = True
            self._show_setup(True)
            return
        self._script_waiting = False
        self.script_log = {"started": datetime.datetime.now().isoformat(timespec="seconds"), "turns": []}
        self._script_index = 0
        self._send(self.script[0])

    def _script_step(self, result: Any) -> None:
        self.script_log.setdefault("turns", []).append({"stop": getattr(result, "stop", "error"),
                                                       "tool_calls": getattr(result, "tool_calls", 0)})
        index = getattr(self, "_script_index", 0) + 1
        self._script_index = index
        if index < len(self.script) and getattr(result, "stop", "") not in ("error", "cap"):
            QTimer.singleShot(500, lambda: self._send(self.script[index]))
            return
        session = self.session
        self.script_log.update({
            "finished": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": getattr(getattr(session, "provider", None), "model", ""),
            "usage": vars(session.usage) if session else {},
            "cost_usd": round(session.cost, 4) if session and session.priced else None,
            "log": str(getattr(session, "log_path", "")),
            "transcript": self._markdown(),
        })
        target = Path(os.environ["SIGMAI_CHAT_SCRIPT"]).with_suffix(".done.json")
        try:
            target.write_text(json.dumps(self.script_log, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def shutdown(self) -> None:
        self._worker.stop_requested = True
        self._thread.quit()
        self._thread.wait(5000)


MODEL_NAMES = {"claude-opus-5-5": "Claude Opus 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-haiku-5-5": "Claude Haiku 5.5"}
_DECIMAL_COMMA = ("pt", "es", "de", "fr", "it")


def _number(value: int, language: str) -> str:
    text = f"{int(value):,}"
    if language.lower().startswith(("pt", "es", "de", "it")):
        return text.replace(",", ".")
    if language.lower().startswith("fr"):
        return text.replace(",", " ")
    return text


def _money(value: float, language: str) -> str:
    text = f"{value:.2f}"
    return text.replace(".", ",") if language.lower().startswith(_DECIMAL_COMMA) else text


def _origin_key(origin: str) -> str:
    return {"cofre": "vault", "sessão": "session", "ambiente": "env"}.get(origin, "session")
