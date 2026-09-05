"""Painel do SIGMAI dentro do QGIS.

A interface anterior era um diálogo único empilhando cinco caixas e onze
botões de mesmo peso visual — "Iniciar", "Parar", "Regenerar Token",
"Copiar Dica MCP", "Abrir Pasta de Diagnósticos" — sem nenhuma indicação do
que fazer primeiro. O token ficava em texto puro na tela, e o botão "Copiar
Dica MCP" copiava um código de pareamento que não era configurável em cliente
nenhum.

O painel foi reorganizado em torno da pergunta que o usuário realmente tem:
*como faço a IA conversar com o meu QGIS?* A aba Conexão responde isso em três
passos numerados. A aba Acesso responde a segunda pergunta: *o que ela pode
fazer aqui dentro?* As demais — Atividade e Avançado — existem para auditar e
ajustar, e ficam fora do caminho de quem está começando.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..cartography.qtcompat import qt_enum
from .client_configs import AI_CLIENTS, build_client_config
from .strings import translate

#: Eventos da trilha de auditoria em linguagem de gente.
EVENT_LABELS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "allowed": "Permitido",
        "denied_read_only": "Bloqueado (somente leitura)",
        "denied_by_user": "Negado por você",
        "denied_remembered": "Negado (categoria recusada antes)",
        "denied_limit": "Bloqueado (limite da sessão)",
        "denied_output_root": "Bloqueado (pasta não autorizada)",
        "denied_never_auto": "Bloqueado (exige ação sua no painel)",
        "denied_no_prompt": "Bloqueado (painel indisponível)",
        "prompt_failed": "Falha ao confirmar",
        "mode_changed": "Modo de acesso alterado",
        "limit_changed": "Limite alterado",
        "output_roots_changed": "Pastas autorizadas alteradas",
        "session_reset": "Sessão reiniciada",
    },
    "en": {
        "allowed": "Allowed",
        "denied_read_only": "Blocked (read only)",
        "denied_by_user": "Denied by you",
        "denied_remembered": "Denied (category refused earlier)",
        "denied_limit": "Blocked (session limit)",
        "denied_output_root": "Blocked (folder not allowed)",
        "denied_never_auto": "Blocked (needs your action in the panel)",
        "denied_no_prompt": "Blocked (panel unavailable)",
        "prompt_failed": "Confirmation failed",
        "mode_changed": "Access mode changed",
        "limit_changed": "Limit changed",
        "output_roots_changed": "Allowed folders changed",
        "session_reset": "Session reset",
    },
}


try:  # pragma: no cover - só falha fora do QGIS
    from qgis.PyQt.QtCore import Qt  # type: ignore
    from qgis.PyQt.QtGui import QPixmap  # type: ignore
    from qgis.PyQt.QtWidgets import (  # type: ignore
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except Exception as exc:  # pragma: no cover
    raise ImportError("O painel do SIGMAI exige PyQt do QGIS.") from exc


ALIGN_CENTER = qt_enum(Qt, "AlignmentFlag", "AlignCenter")
ALIGN_LEFT = qt_enum(Qt, "AlignmentFlag", "AlignLeft")
ALIGN_RIGHT = qt_enum(Qt, "AlignmentFlag", "AlignRight")
ALIGN_TOP = qt_enum(Qt, "AlignmentFlag", "AlignTop")
SMOOTH = qt_enum(Qt, "TransformationMode", "SmoothTransformation")
# Texto da Ajuda selecionável: a pessoa precisa poder copiar as frases de exemplo.
TEXT_SELECTABLE = qt_enum(Qt, "TextInteractionFlag", "TextSelectableByMouse")
NO_FRAME = qt_enum(QFrame, "Shape", "NoFrame")
ECHO_PASSWORD = qt_enum(QLineEdit, "EchoMode", "Password")
ECHO_NORMAL = qt_enum(QLineEdit, "EchoMode", "Normal")
NO_EDIT = qt_enum(QAbstractItemView, "EditTrigger", "NoEditTriggers")
STRETCH = qt_enum(QHeaderView, "ResizeMode", "Stretch")
# No PyQt6 os enums só existem no escopo qualificado: QSizePolicy.Fixed
# some e vira QSizePolicy.Policy.Fixed. Era o que impedia o painel de abrir
# no QGIS 4.
SIZE_FIXED = qt_enum(QSizePolicy, "Policy", "Fixed")
RESIZE_CONTENTS = qt_enum(QHeaderView, "ResizeMode", "ResizeToContents")


def _card(object_name: str = "stepCard") -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    return frame


def _label(text: str, object_name: str = "", wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(wrap)
    return label


class SigmaiPanel(QWidget):
    """O painel. Conversa com o plugin através de um pequeno protocolo.

    O ``controller`` precisa oferecer: ``server``, ``consent``, ``token``,
    ``session_id``, ``language``, ``start_bridge()``, ``stop_bridge()``,
    ``regenerate_token()``, ``session_file_path()``, ``settings_get/set``,
    ``toggle_dev_mode()``, ``set_language()`` e ``run_self_test()``. Manter o
    painel ignorante quanto ao resto do plugin permite renderizá-lo e testá-lo
    com um controlador falso, fora do QGIS interativo.
    """

    def __init__(self, controller: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("sigmaiRoot")
        self._building = True
        self._build()
        self._building = False
        self.refresh()

    # -- utilidades -------------------------------------------------------
    def tr_(self, key: str, **kwargs: Any) -> str:
        return translate(getattr(self.controller, "language", "pt-BR"), key, **kwargs)

    def _icons_dir(self) -> Path:
        return Path(__file__).resolve().parents[1] / "icons"

    # -- construção -------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)
        outer.addWidget(self._build_header())

        self.tabs = QTabWidget()
        # Sem isto o Qt elide o rótulo da aba quando a folha de estilo muda
        # a métrica do texto depois do cálculo inicial de largura.
        self.tabs.setElideMode(qt_enum(Qt, 'TextElideMode', 'ElideNone'))
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.addTab(self._scrolled(self._build_connection_tab()), self.tr_("tab_connection"))
        self.tabs.addTab(self._scrolled(self._build_access_tab()), self.tr_("tab_access"))
        self.tabs.addTab(self._scrolled(self._build_activity_tab()), self.tr_("tab_activity"))
        self.tabs.addTab(self._scrolled(self._build_advanced_tab()), self.tr_("tab_advanced"))
        self.tabs.addTab(self._scrolled(self._build_help_tab()), self.tr_("tab_help"))
        outer.addWidget(self.tabs, 1)

    def _scrolled(self, widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(NO_FRAME)
        area.setWidget(widget)
        return area

    def _build_header(self) -> QWidget:
        header = _card("headerFrame")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        logo = QLabel()
        logo.setObjectName("logoPanel")
        pixmap = QPixmap(str(self._icons_dir() / "sigmai_logo_full.png"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToHeight(46, SMOOTH))
            logo.setAlignment(ALIGN_CENTER)
            logo.setSizePolicy(SIZE_FIXED, SIZE_FIXED)
            layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title_label = _label("SIGMAI", "brandTitle")
        self.subtitle_label = _label(self.tr_("subtitle"), "brandSubtitle")
        self.context_label = _label(self.tr_("context"), "brandContext")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        titles.addWidget(self.context_label)
        layout.addLayout(titles, 1)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.language_button = QPushButton(self.tr_("language_button"))
        self.language_button.setObjectName("linkButton")
        self.language_button.clicked.connect(self._toggle_language)
        self.status_pill = _label(self.tr_("offline"), "pillOffline")
        self.status_pill.setAlignment(ALIGN_CENTER)
        right.addWidget(self.language_button, 0, ALIGN_RIGHT)
        right.addWidget(self.status_pill, 0, ALIGN_RIGHT)
        right.addStretch(1)
        layout.addLayout(right)
        return header

    # -- aba 1: conexão ---------------------------------------------------
    def _build_connection_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Passo 1
        card, body = self._step_card(1, "step1_title", "step1_hint")
        self.bridge_state_label = _label("", "helpText", wrap=True)
        self.bridge_button = QPushButton(self.tr_("step1_start"))
        self.bridge_button.setObjectName("primaryButton")
        self.bridge_button.clicked.connect(self._toggle_bridge)
        row = QHBoxLayout()
        row.addWidget(self.bridge_button)
        row.addWidget(self.bridge_state_label, 1)
        body.addLayout(row)
        self.step1_card = card
        layout.addWidget(card)

        # Passo 2
        card, body = self._step_card(2, "step2_title", "step2_hint")
        client_row = QHBoxLayout()
        self.client_label = _label(self.tr_("step2_client") + ":", "helpText")
        self.client_combo = QComboBox()
        for key, spec in AI_CLIENTS.items():
            self.client_combo.addItem(spec["label"], key)
        self.client_combo.currentIndexChanged.connect(self._refresh_client_config)
        client_row.addWidget(self.client_label)
        client_row.addWidget(self.client_combo, 1)
        body.addLayout(client_row)

        self.config_where_label = _label("", "helpText", wrap=True)
        body.addWidget(self.config_where_label)
        self.config_block = QPlainTextEdit()
        self.config_block.setObjectName("codeBlock")
        self.config_block.setReadOnly(True)
        self.config_block.setMinimumHeight(130)
        body.addWidget(self.config_block)
        self.config_note_label = _label("", "helpText", wrap=True)
        body.addWidget(self.config_note_label)

        buttons = QHBoxLayout()
        self.copy_config_button = QPushButton(self.tr_("step2_copy"))
        self.copy_config_button.setObjectName("primaryButton")
        self.copy_config_button.clicked.connect(self._copy_config)
        self.open_config_button = QPushButton(self.tr_("step2_open_folder"))
        self.open_config_button.clicked.connect(self._open_config_folder)
        buttons.addWidget(self.copy_config_button)
        buttons.addWidget(self.open_config_button)
        buttons.addStretch(1)
        body.addLayout(buttons)
        self.copy_feedback_label = _label("", "noticeOk", wrap=True)
        self.copy_feedback_label.setVisible(False)
        body.addWidget(self.copy_feedback_label)
        self.step2_card = card
        layout.addWidget(card)

        # Passo 3
        card, body = self._step_card(3, "step3_title", "step3_hint")
        run_row = QHBoxLayout()
        self.self_test_button = QPushButton(self.tr_("step3_run"))
        self.self_test_button.clicked.connect(self._run_self_test)
        run_row.addWidget(self.self_test_button)
        run_row.addStretch(1)
        body.addLayout(run_row)
        self.self_test_output = _label(self.tr_("step3_never"), "helpText", wrap=True)
        body.addWidget(self.self_test_output)
        self.step3_card = card
        layout.addWidget(card)

        layout.addStretch(1)
        return page

    def _step_card(self, number: int, title_key: str, hint_key: str) -> tuple[QFrame, QVBoxLayout]:
        card = _card()
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 12, 14, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)

        badge = _label(str(number), "stepNumber")
        badge.setAlignment(ALIGN_CENTER)
        grid.addWidget(badge, 0, 0, 2, 1, ALIGN_TOP)

        title = _label(self.tr_(title_key), "stepTitle")
        hint = _label(self.tr_(hint_key), "stepHint", wrap=True)
        grid.addWidget(title, 0, 1)
        grid.addWidget(hint, 1, 1)

        body = QVBoxLayout()
        body.setSpacing(8)
        body.setContentsMargins(0, 8, 0, 0)
        grid.addLayout(body, 2, 1)
        grid.setColumnStretch(1, 1)

        card.setProperty("_title_label", title)
        card.setProperty("_hint_label", hint)
        card.setProperty("_badge", badge)
        card.setProperty("_title_key", title_key)
        card.setProperty("_hint_key", hint_key)
        return card, body

    # -- aba 2: acesso ----------------------------------------------------
    def _build_access_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        card = _card()
        body = QVBoxLayout(card)
        body.setContentsMargins(14, 12, 14, 14)
        body.setSpacing(6)
        self.access_title = _label(self.tr_("access_title"), "sectionTitle")
        self.access_hint = _label(self.tr_("access_hint"), "helpText", wrap=True)
        body.addWidget(self.access_title)
        body.addWidget(self.access_hint)

        self.mode_buttons: dict[str, QRadioButton] = {}
        self.mode_hints: dict[str, QLabel] = {}
        for mode, title_key, hint_key in (
            ("read_only", "mode_read_only", "mode_read_only_hint"),
            ("ask", "mode_ask", "mode_ask_hint"),
            ("allow_session", "mode_allow", "mode_allow_hint"),
        ):
            button = QRadioButton(self.tr_(title_key))
            button.toggled.connect(lambda checked, value=mode: self._set_mode(value) if checked else None)
            hint = _label(self.tr_(hint_key), "helpText", wrap=True)
            hint.setContentsMargins(24, 0, 0, 6)
            body.addWidget(button)
            body.addWidget(hint)
            self.mode_buttons[mode] = button
            self.mode_hints[mode] = hint
            button.setProperty("_key", title_key)
            hint.setProperty("_key", hint_key)
        layout.addWidget(card)

        # Pastas autorizadas
        self.folders_group = QGroupBox(self.tr_("folders_title"))
        folders_layout = QVBoxLayout(self.folders_group)
        self.folders_hint = _label(self.tr_("folders_hint"), "helpText", wrap=True)
        folders_layout.addWidget(self.folders_hint)
        self.folders_list = QListWidget()
        self.folders_list.setMaximumHeight(96)
        folders_layout.addWidget(self.folders_list)
        folder_buttons = QHBoxLayout()
        self.folder_add_button = QPushButton(self.tr_("folders_add"))
        self.folder_add_button.clicked.connect(self._add_folder)
        self.folder_remove_button = QPushButton(self.tr_("folders_remove"))
        self.folder_remove_button.clicked.connect(self._remove_folder)
        folder_buttons.addWidget(self.folder_add_button)
        folder_buttons.addWidget(self.folder_remove_button)
        folder_buttons.addStretch(1)
        folders_layout.addLayout(folder_buttons)
        layout.addWidget(self.folders_group)

        # Limites
        self.limits_group = QGroupBox(self.tr_("limits_title"))
        limits_layout = QVBoxLayout(self.limits_group)
        self.limits_hint = _label(self.tr_("limits_hint"), "helpText", wrap=True)
        limits_layout.addWidget(self.limits_hint)
        form = QFormLayout()
        self.limit_widgets: dict[str, tuple[QSpinBox, QProgressBar, QLabel]] = {}
        for key, label_key in (
            ("writes_per_session", "limit_writes"),
            ("exports_per_session", "limit_exports"),
            ("processing_runs_per_session", "limit_processing"),
        ):
            spin = QSpinBox()
            spin.setRange(0, 100000)
            spin.setSingleStep(10)
            spin.valueChanged.connect(lambda value, name=key: self._set_limit(name, value))
            bar = QProgressBar()
            bar.setTextVisible(True)
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(spin)
            row_layout.addWidget(bar, 1)
            field_label = QLabel(self.tr_(label_key))
            field_label.setProperty("_key", label_key)
            form.addRow(field_label, row)
            self.limit_widgets[key] = (spin, bar, field_label)
        limits_layout.addLayout(form)
        self.limits_reset_button = QPushButton(self.tr_("limits_reset"))
        self.limits_reset_button.clicked.connect(self._reset_session)
        limits_layout.addWidget(self.limits_reset_button, 0, ALIGN_LEFT)
        layout.addWidget(self.limits_group)

        layout.addStretch(1)
        return page

    # -- aba 3: atividade -------------------------------------------------
    def _build_activity_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.activity_title = _label(self.tr_("activity_title"), "sectionTitle")
        self.activity_hint = _label(self.tr_("activity_hint"), "helpText", wrap=True)
        layout.addWidget(self.activity_title)
        layout.addWidget(self.activity_hint)

        self.activity_table = QTableWidget(0, 4)
        self.activity_table.setHorizontalHeaderLabels([
            self.tr_("col_time"), self.tr_("col_event"), self.tr_("col_action"), self.tr_("col_detail"),
        ])
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.setEditTriggers(NO_EDIT)
        header = self.activity_table.horizontalHeader()
        header.setSectionResizeMode(0, RESIZE_CONTENTS)
        header.setSectionResizeMode(1, RESIZE_CONTENTS)
        header.setSectionResizeMode(2, RESIZE_CONTENTS)
        header.setSectionResizeMode(3, STRETCH)
        layout.addWidget(self.activity_table, 1)

        buttons = QHBoxLayout()
        self.activity_refresh_button = QPushButton(self.tr_("activity_refresh"))
        self.activity_refresh_button.clicked.connect(self.refresh_activity)
        self.activity_export_button = QPushButton(self.tr_("activity_export"))
        self.activity_export_button.clicked.connect(self._export_activity)
        buttons.addWidget(self.activity_refresh_button)
        buttons.addWidget(self.activity_export_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    # -- aba 5: ajuda -----------------------------------------------------
    def _build_help_tab(self) -> QWidget:
        """A aba que explica a ferramenta a quem nunca usou um SIG.

        As outras abas assumem que a pessoa sabe o que é uma ponte, um token e
        um layout. Esta não assume nada: diz o que a ferramenta é, o que dizer
        ao assistente, o que ele vai perguntar de volta e por que às vezes ele
        recusa.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.help_title = _label(self.tr_("help_title"), "sectionTitle")
        layout.addWidget(self.help_title)

        self.help_blocks: list[tuple[QLabel, QLabel, str, str]] = []
        for title_key, body_key in (
            ("help_what_title", "help_what"),
            ("help_try_title", "help_try"),
            ("help_ask_title", "help_ask"),
            ("help_quality_title", "help_quality"),
            ("help_refuse_title", "help_refuse"),
            ("help_privacy_title", "help_privacy"),
        ):
            card = _card()
            inner = QVBoxLayout(card)
            inner.setContentsMargins(14, 12, 14, 12)
            inner.setSpacing(4)
            title = _label(self.tr_(title_key), "stepTitle")
            body = _label(self.tr_(body_key), "helpText", wrap=True)
            body.setTextInteractionFlags(TEXT_SELECTABLE)
            inner.addWidget(title)
            inner.addWidget(body)
            layout.addWidget(card)
            self.help_blocks.append((title, body, title_key, body_key))

        self.help_docs = _label(self.tr_("help_docs"), "helpText", wrap=True)
        self.help_docs.setTextInteractionFlags(TEXT_SELECTABLE)
        layout.addWidget(self.help_docs)

        self.help_authorship = _label(self.tr_("about_map_authorship"), "helpText", wrap=True)
        layout.addWidget(self.help_authorship)

        layout.addStretch(1)
        return page

    # -- aba 4: avançado --------------------------------------------------
    def _build_advanced_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.endpoint_group = QGroupBox(self.tr_("advanced_endpoint"))
        form = QFormLayout(self.endpoint_group)
        self.host_value = QLabel("127.0.0.1")
        self.port_value = QLabel("—")
        self.token_field = QLineEdit()
        self.token_field.setObjectName("codeField")
        self.token_field.setReadOnly(True)
        self.token_field.setEchoMode(ECHO_PASSWORD)
        self.token_show_button = QPushButton(self.tr_("advanced_show"))
        self.token_show_button.setObjectName("linkButton")
        self.token_show_button.clicked.connect(self._toggle_token_visibility)
        self.token_copy_button = QPushButton(self.tr_("advanced_copy_token"))
        self.token_copy_button.setObjectName("linkButton")
        self.token_copy_button.clicked.connect(self._copy_token)
        token_row = QWidget()
        token_layout = QHBoxLayout(token_row)
        token_layout.setContentsMargins(0, 0, 0, 0)
        token_layout.addWidget(self.token_field, 1)
        token_layout.addWidget(self.token_show_button)
        token_layout.addWidget(self.token_copy_button)

        self.session_field = QLineEdit()
        self.session_field.setObjectName("codeField")
        self.session_field.setReadOnly(True)

        self.host_label = QLabel(self.tr_("advanced_host"))
        self.port_label = QLabel(self.tr_("advanced_port"))
        self.token_label = QLabel(self.tr_("advanced_token"))
        self.session_label = QLabel(self.tr_("advanced_session_file"))
        form.addRow(self.host_label, self.host_value)
        form.addRow(self.port_label, self.port_value)
        form.addRow(self.token_label, token_row)
        form.addRow(self.session_label, self.session_field)
        self.token_warning = _label(self.tr_("advanced_token_warning"), "noticeWarn", wrap=True)
        form.addRow(self.token_warning)
        layout.addWidget(self.endpoint_group)

        self.autostart_check = QCheckBox(self.tr_("advanced_autostart"))
        self.autostart_check.toggled.connect(lambda value: self._settings_set("auto_start", value))
        self.write_session_check = QCheckBox(self.tr_("advanced_write_session"))
        self.write_session_check.toggled.connect(lambda value: self._settings_set("write_session_file", value))
        self.persist_token_check = QCheckBox(self.tr_("advanced_persist_token"))
        self.persist_token_check.toggled.connect(lambda value: self._settings_set("persist_token", value))
        self.persist_hint = _label(self.tr_("advanced_persist_hint"), "helpText", wrap=True)
        self.persist_hint.setContentsMargins(24, 0, 0, 0)
        for widget in (self.autostart_check, self.write_session_check, self.persist_token_check, self.persist_hint):
            layout.addWidget(widget)

        tools = QHBoxLayout()
        self.regenerate_button = QPushButton(self.tr_("advanced_regenerate"))
        self.regenerate_button.clicked.connect(self._regenerate_token)
        self.logs_button = QPushButton(self.tr_("advanced_open_logs"))
        self.logs_button.clicked.connect(self._open_logs)
        tools.addWidget(self.regenerate_button)
        tools.addWidget(self.logs_button)
        tools.addStretch(1)
        layout.addLayout(tools)

        self.dev_group = QGroupBox(self.tr_("dev_title"))
        dev_layout = QVBoxLayout(self.dev_group)
        self.dev_hint = _label(self.tr_("dev_hint"), "helpText", wrap=True)
        self.dev_warning = _label(self.tr_("dev_warning"), "noticeDanger", wrap=True)
        self.dev_button = QPushButton(self.tr_("dev_enable"))
        self.dev_button.setObjectName("devButtonOff")
        self.dev_button.clicked.connect(self._toggle_dev_mode)
        dev_layout.addWidget(self.dev_hint)
        dev_layout.addWidget(self.dev_warning)
        dev_layout.addWidget(self.dev_button, 0, ALIGN_LEFT)
        layout.addWidget(self.dev_group)

        self.about_group = QGroupBox(self.tr_("about_title"))
        about_layout = QVBoxLayout(self.about_group)
        version = str(self._call("plugin_version") or "")
        self.about_plugin_label = _label(self.tr_("about_plugin"), "helpText", wrap=True)
        self.about_license_label = _label(self.tr_("about_license", version=version), "helpText", wrap=True)
        self.about_authorship_label = _label(self.tr_("about_map_authorship"), "helpText", wrap=True)
        for widget in (self.about_plugin_label, self.about_license_label, self.about_authorship_label):
            about_layout.addWidget(widget)
        layout.addWidget(self.about_group)

        layout.addStretch(1)
        return page

    # -- ações ------------------------------------------------------------
    def _call(self, name: str, *args: Any) -> Any:
        handler: Callable | None = getattr(self.controller, name, None)
        if handler is None:
            return None
        try:
            return handler(*args)
        except Exception:
            return None

    def _toggle_bridge(self) -> None:
        server = getattr(self.controller, "server", None)
        if server is not None and getattr(server, "running", False):
            self._call("stop_bridge")
        else:
            self._call("start_bridge")
        self.refresh()

    def _toggle_language(self) -> None:
        current = getattr(self.controller, "language", "pt-BR")
        self._call("set_language", "en" if current == "pt-BR" else "pt-BR")
        self.retranslate()
        self.refresh()

    def _set_mode(self, mode: str) -> None:
        if self._building:
            return
        consent = getattr(self.controller, "consent", None)
        if consent is not None:
            consent.set_mode(mode)
        self._settings_set("consent_mode", mode)

    def _set_limit(self, name: str, value: int) -> None:
        if self._building:
            return
        consent = getattr(self.controller, "consent", None)
        if consent is not None:
            consent.set_limit(name, int(value))
        self._settings_set(f"limit_{name}", int(value))

    def _reset_session(self) -> None:
        consent = getattr(self.controller, "consent", None)
        if consent is not None:
            consent.reset_session()
        self.refresh()

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.tr_("folders_add"))
        if not folder:
            return
        consent = getattr(self.controller, "consent", None)
        if consent is not None:
            roots = list(consent.output_roots) + [folder]
            consent.set_output_roots(roots)
            self._settings_set("output_roots", "|".join(roots))
        self.refresh()

    def _remove_folder(self) -> None:
        item = self.folders_list.currentItem()
        if item is None:
            return
        consent = getattr(self.controller, "consent", None)
        if consent is not None:
            roots = [root for root in consent.output_roots if root != item.text()]
            consent.set_output_roots(roots)
            self._settings_set("output_roots", "|".join(roots))
        self.refresh()

    def _settings_set(self, key: str, value: Any) -> None:
        if self._building:
            return
        self._call("settings_set", key, value)

    def _current_client(self) -> str:
        data = self.client_combo.currentData()
        return str(data or "claude_desktop")

    def _client_config(self) -> dict[str, Any]:
        session = self._call("session_file_path")
        return build_client_config(
            self._current_client(),
            package_root=Path(__file__).resolve().parents[1],
            session_file=str(session) if session else None,
        )

    def _refresh_client_config(self) -> None:
        config = self._client_config()
        self.config_block.setPlainText(config["snippet"])
        self.config_where_label.setText(f"<b>{self.tr_('step2_where')}:</b> <code>{config['config_path']}</code>")
        language = getattr(self.controller, "language", "pt-BR")
        self.config_note_label.setText(config["note_pt"] if language == "pt-BR" else config["note_en"])
        self.copy_feedback_label.setVisible(False)

    def _copy_config(self) -> None:
        self._call("copy_to_clipboard", self.config_block.toPlainText())
        self.copy_feedback_label.setText(self.tr_("step2_copied"))
        self.copy_feedback_label.setVisible(True)

    def _open_config_folder(self) -> None:
        self._call("open_path", self._client_config()["config_path"])

    def _copy_token(self) -> None:
        self._call("copy_to_clipboard", getattr(self.controller, "token", ""))

    def _toggle_token_visibility(self) -> None:
        hidden = self.token_field.echoMode() == ECHO_PASSWORD
        self.token_field.setEchoMode(ECHO_NORMAL if hidden else ECHO_PASSWORD)
        self.token_show_button.setText(self.tr_("advanced_hide") if hidden else self.tr_("advanced_show"))

    def _regenerate_token(self) -> None:
        self._call("regenerate_token")
        self.refresh()

    def _open_logs(self) -> None:
        self._call("open_diagnostics")

    def _toggle_dev_mode(self) -> None:
        self._call("toggle_dev_mode")
        self.refresh()

    def _run_self_test(self) -> None:
        self.self_test_output.setText(self.tr_("step3_running"))
        self.self_test_button.setEnabled(False)
        try:
            results = self._call("run_self_test") or []
        finally:
            self.self_test_button.setEnabled(True)
        if not results:
            self.self_test_output.setText(self.tr_("step3_never"))
            return
        lines = []
        for item in results:
            mark = "✓" if item.get("ok") else "✗"
            colour = "#0B6E4F" if item.get("ok") else "#A3231F"
            detail = item.get("detail", "")
            lines.append(f'<span style="color:{colour}">{mark}</span> <b>{item.get("label","")}</b> — {detail}')
        self.self_test_output.setText("<br>".join(lines))

    def _export_activity(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.tr_("activity_export"), "sigmai_atividade.json", "JSON (*.json)")
        if not path:
            return
        consent = getattr(self.controller, "consent", None)
        payload = {
            "generated_at": self._call("utc_now"),
            "status": consent.status() if consent is not None else {},
            "audit": consent.recent_audit(500) if consent is not None else [],
        }
        try:
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass

    # -- atualização ------------------------------------------------------
    def refresh(self) -> None:
        server = getattr(self.controller, "server", None)
        running = bool(getattr(server, "running", False))
        host = getattr(server, "host", "127.0.0.1")
        port = getattr(server, "port", "—")
        qgis_version = getattr(server, "qgis_version", "") or "?"

        self.status_pill.setText(self.tr_("online") if running else self.tr_("offline"))
        self.status_pill.setObjectName("pillOnline" if running else "pillOffline")
        self._repolish(self.status_pill)

        self.bridge_button.setText(self.tr_("step1_stop") if running else self.tr_("step1_start"))
        self.bridge_button.setObjectName("dangerButton" if running else "primaryButton")
        self._repolish(self.bridge_button)
        self.bridge_state_label.setText(
            self.tr_("step1_running", host=host, port=port, qgis=qgis_version) if running else self.tr_("step1_stopped")
        )
        # O passo pendente ganha a borda destacada: o usuário vê onde continuar.
        self._mark_step(self.step1_card, active=not running)
        self._mark_step(self.step2_card, active=running)

        self.host_value.setText(str(host))
        self.port_value.setText(str(port))
        self.token_field.setText(str(getattr(self.controller, "token", "")))
        session = self._call("session_file_path")
        self.session_field.setText(str(session) if session else "")

        for key, checkbox in (
            ("auto_start", self.autostart_check),
            ("write_session_file", self.write_session_check),
            ("persist_token", self.persist_token_check),
        ):
            value = self._call("settings_get", key, True)
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(value))
            checkbox.blockSignals(False)

        dev_on = bool(getattr(server, "unsafe_developer_mode", False))
        self.dev_button.setText(self.tr_("dev_disable") if dev_on else self.tr_("dev_enable"))
        self.dev_button.setObjectName("devButtonOn" if dev_on else "devButtonOff")
        self._repolish(self.dev_button)

        self._refresh_consent()
        self._refresh_client_config()
        self.refresh_activity()

    def _refresh_consent(self) -> None:
        consent = getattr(self.controller, "consent", None)
        if consent is None:
            return
        status = consent.status()
        self._building = True
        try:
            button = self.mode_buttons.get(status["mode"])
            if button is not None:
                button.setChecked(True)
            self.folders_list.clear()
            for root in status["output_roots"]:
                self.folders_list.addItem(root)
            for key, (spin, bar, _) in self.limit_widgets.items():
                limit = int(status["limits"].get(key, 0))
                used = int(status["counters"].get(key, 0))
                spin.setValue(limit)
                bar.setMaximum(max(1, limit))
                bar.setValue(min(used, max(1, limit)))
                bar.setFormat(f"{used} / {limit}")
        finally:
            self._building = False

    def refresh_activity(self) -> None:
        consent = getattr(self.controller, "consent", None)
        entries = consent.recent_audit(120) if consent is not None else []
        entries = list(reversed(entries))
        self.activity_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            request = entry.get("request") or {}
            timestamp = str(entry.get("timestamp", ""))[11:19]
            detail = entry.get("reason") or "; ".join(request.get("output_paths", [])) or entry.get("mode", "")
            language = getattr(self.controller, "language", "pt-BR")
            raw_event = str(entry.get("event", ""))
            event = EVENT_LABELS.get(language, EVENT_LABELS["en"]).get(raw_event, raw_event)
            for column, value in enumerate((timestamp, event, str(request.get("action", "")), str(detail))):
                self.activity_table.setItem(row, column, QTableWidgetItem(value))

    def _mark_step(self, card: QFrame, active: bool) -> None:
        card.setObjectName("stepCardActive" if active else "stepCard")
        self._repolish(card)
        badge = card.property("_badge")
        if isinstance(badge, QLabel):
            badge.setObjectName("stepNumber" if active else "stepNumberDone")
            self._repolish(badge)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)

    # -- idioma -----------------------------------------------------------
    def _retranslate_help(self) -> None:
        """A aba de Ajuda é toda texto: sem isto ela ficaria em português no modo EN."""
        self.help_title.setText(self.tr_("help_title"))
        for title, body, title_key, body_key in getattr(self, "help_blocks", []):
            title.setText(self.tr_(title_key))
            body.setText(self.tr_(body_key))
        self.help_docs.setText(self.tr_("help_docs"))
        self.help_authorship.setText(self.tr_("about_map_authorship"))

    def retranslate(self) -> None:
        self.subtitle_label.setText(self.tr_("subtitle"))
        self.context_label.setText(self.tr_("context"))
        self.language_button.setText(self.tr_("language_button"))
        for index, key in enumerate(
            ("tab_connection", "tab_access", "tab_activity", "tab_advanced", "tab_help")
        ):
            self.tabs.setTabText(index, self.tr_(key))
        for card in (self.step1_card, self.step2_card, self.step3_card):
            title = card.property("_title_label")
            hint = card.property("_hint_label")
            if isinstance(title, QLabel):
                title.setText(self.tr_(str(card.property("_title_key"))))
            if isinstance(hint, QLabel):
                hint.setText(self.tr_(str(card.property("_hint_key"))))
        self.client_label.setText(self.tr_("step2_client") + ":")
        self.copy_config_button.setText(self.tr_("step2_copy"))
        self.open_config_button.setText(self.tr_("step2_open_folder"))
        self.self_test_button.setText(self.tr_("step3_run"))
        self.access_title.setText(self.tr_("access_title"))
        self.access_hint.setText(self.tr_("access_hint"))
        for mode, button in self.mode_buttons.items():
            button.setText(self.tr_(str(button.property("_key"))))
            self.mode_hints[mode].setText(self.tr_(str(self.mode_hints[mode].property("_key"))))
        self.folders_group.setTitle(self.tr_("folders_title"))
        self.folders_hint.setText(self.tr_("folders_hint"))
        self.folder_add_button.setText(self.tr_("folders_add"))
        self.folder_remove_button.setText(self.tr_("folders_remove"))
        self.limits_group.setTitle(self.tr_("limits_title"))
        self.limits_hint.setText(self.tr_("limits_hint"))
        for _, (_, _, field_label) in self.limit_widgets.items():
            field_label.setText(self.tr_(str(field_label.property("_key"))))
        self.limits_reset_button.setText(self.tr_("limits_reset"))
        self.activity_title.setText(self.tr_("activity_title"))
        self.activity_hint.setText(self.tr_("activity_hint"))
        self.activity_table.setHorizontalHeaderLabels([
            self.tr_("col_time"), self.tr_("col_event"), self.tr_("col_action"), self.tr_("col_detail"),
        ])
        self.activity_refresh_button.setText(self.tr_("activity_refresh"))
        self.activity_export_button.setText(self.tr_("activity_export"))
        self.endpoint_group.setTitle(self.tr_("advanced_endpoint"))
        self.host_label.setText(self.tr_("advanced_host"))
        self.port_label.setText(self.tr_("advanced_port"))
        self.token_label.setText(self.tr_("advanced_token"))
        self.session_label.setText(self.tr_("advanced_session_file"))
        self.token_warning.setText(self.tr_("advanced_token_warning"))
        self.autostart_check.setText(self.tr_("advanced_autostart"))
        self.write_session_check.setText(self.tr_("advanced_write_session"))
        self.persist_token_check.setText(self.tr_("advanced_persist_token"))
        self.persist_hint.setText(self.tr_("advanced_persist_hint"))
        self.regenerate_button.setText(self.tr_("advanced_regenerate"))
        self.logs_button.setText(self.tr_("advanced_open_logs"))
        self.dev_group.setTitle(self.tr_("dev_title"))
        self.dev_hint.setText(self.tr_("dev_hint"))
        self.dev_warning.setText(self.tr_("dev_warning"))
        self.about_group.setTitle(self.tr_("about_title"))
        self.about_plugin_label.setText(self.tr_("about_plugin"))
        self.about_license_label.setText(self.tr_("about_license", version=str(self._call("plugin_version") or "")))
        self.about_authorship_label.setText(self.tr_("about_map_authorship"))
        self._retranslate_help()

