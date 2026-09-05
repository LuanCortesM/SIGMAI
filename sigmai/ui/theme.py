"""Folha de estilo do painel do SIGMAI, em tema claro e em tema escuro.

O painel vive dentro do QGIS, e o QGIS tem temas próprios ("Night Mapping",
"Blend of Gray") que aplicam uma folha de estilo e uma paleta escuras ao
aplicativo inteiro. A versão anterior deste módulo só tinha a paleta clara e
só estilizava os widgets que nomeava: tudo o que ficava de fora — o texto dos
botões de rádio, os rótulos de formulário, o fundo das páginas, o título das
caixas de grupo, os spinboxes e as barras de rolagem — herdava o tema do QGIS.
Em tema escuro o resultado era um cartão branco com texto cinza-claro dentro,
rádios com fundo preto e rótulos ilegíveis.

Duas decisões corrigem isso de vez:

1. **Duas paletas, mesmo desenho.** ``Palette`` descreve as cores; a folha é
   uma só e recebe a paleta. O tema escuro não é o claro invertido: as
   superfícies são azul-ardósia, o verde da marca sobe um tom para manter
   contraste sobre fundo escuro, e os avisos usam pastel sobre fundo fechado.
   Todo par texto/fundo foi conferido acima de 4,5:1 (WCAG AA).
2. **A folha é completa.** Ela declara fundo e cor de texto de TODO widget que
   o painel usa — inclusive o fundo transparente de rótulos, rádios e caixas de
   seleção, o viewport das áreas de rolagem, o popup das caixas de combinação,
   as barras de rolagem e as células de tabela. Nada é deixado para o tema do
   aplicativo decidir, em nenhum dos dois modos.

Qual paleta usar é decidido por :func:`resolve_theme`: automático (segue a
paleta do QGIS — ver :func:`is_dark_palette`), ou forçado pelo usuário.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

THEME_AUTO = "auto"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_PREFERENCES = (THEME_AUTO, THEME_LIGHT, THEME_DARK)


@dataclass(frozen=True)
class Palette:
    """As cores de um tema. Os nomes são os papéis, não as cores."""

    ink: str            # texto principal
    ink_soft: str       # texto de apoio (dicas, rodapés)
    ink_muted: str      # texto desabilitado
    line: str           # bordas e divisórias
    surface: str        # cartões, campos, popups
    canvas: str         # fundo das páginas
    field: str          # fundo de campos de código
    brand_deep: str     # cabeçalho e títulos de seção
    brand: str          # verde da marca em texto e abas
    brand_bright: str   # verde da marca em botões e destaques
    accent: str         # seleção
    danger: str
    danger_soft: str
    danger_line: str
    warn: str
    warn_soft: str
    warn_line: str
    ok: str             # ✓ do autoteste
    header_text: str    # texto secundário sobre o cabeçalho escuro
    disabled_surface: str
    pill_offline: str
    pill_offline_text: str
    scrollbar: str


LIGHT = Palette(
    ink="#16232B",
    ink_soft="#5B6B77",      # 5,4:1 sobre #FFFFFF
    ink_muted="#9AAAB4",
    line="#D6E0E6",
    surface="#FFFFFF",
    canvas="#F4F7F9",
    field="#F7FAFB",
    brand_deep="#062A3A",
    brand="#0B6E4F",         # 6,0:1 sobre #FFFFFF
    brand_bright="#00A86B",
    accent="#20E39A",
    danger="#A3231F",
    danger_soft="#FDF3F2",
    danger_line="#F0C4C2",
    warn="#8A5A00",
    warn_soft="#FFF8E8",
    warn_line="#F0D9A8",
    ok="#0B6E4F",
    header_text="#C4D4DD",
    disabled_surface="#FAFCFD",
    pill_offline="#33454F",
    pill_offline_text="#C4D4DD",
    scrollbar="#C5D1D9",
)

DARK = Palette(
    ink="#E6EDF1",           # 12,9:1 sobre #242D34
    ink_soft="#A9B7C1",      # 7,1:1 sobre #242D34
    ink_muted="#6E7E89",
    line="#3B4954",
    surface="#242D34",
    canvas="#1A2127",
    field="#1E262C",
    brand_deep="#0A3346",
    brand="#3DD598",         # 8,4:1 sobre #242D34
    brand_bright="#00A86B",
    accent="#20E39A",
    danger="#F5928C",        # 7,6:1 sobre #3A2323
    danger_soft="#3A2323",
    danger_line="#6B3A37",
    warn="#F2C46D",          # 9,2:1 sobre #3A3018
    warn_soft="#3A3018",
    warn_line="#6B5A2A",
    ok="#3DD598",
    header_text="#C4D4DD",
    disabled_surface="#202830",
    pill_offline="#3B4954",
    pill_offline_text="#C4D4DD",
    scrollbar="#4A5A66",
)

PALETTES: dict[str, Palette] = {THEME_LIGHT: LIGHT, THEME_DARK: DARK}

# Compatibilidade com quem importava as constantes soltas do tema claro.
INK, INK_SOFT, LINE, SURFACE, CANVAS = LIGHT.ink, LIGHT.ink_soft, LIGHT.line, LIGHT.surface, LIGHT.canvas
BRAND_DEEP, BRAND, BRAND_BRIGHT, ACCENT = LIGHT.brand_deep, LIGHT.brand, LIGHT.brand_bright, LIGHT.accent
DANGER, DANGER_SOFT, WARN, WARN_SOFT = LIGHT.danger, LIGHT.danger_soft, LIGHT.warn, LIGHT.warn_soft


def is_dark_palette(palette: Any) -> bool:
    """O QGIS está num tema escuro?

    Lê a cor de fundo de janela da paleta do aplicativo: abaixo de 50% de
    luminosidade é tema escuro. É o mesmo critério que o próprio Qt usa para
    ``QStyleHints.colorScheme`` nas versões que o expõem, e funciona em todas
    as versões de Qt 5 e 6 que o QGIS 3.28+ usa.
    """
    try:
        try:
            from qgis.PyQt.QtGui import QPalette  # type: ignore
        except Exception:  # pragma: no cover - fora do QGIS
            from PyQt5.QtGui import QPalette  # type: ignore
        role = getattr(getattr(QPalette, "ColorRole", QPalette), "Window")
        colour = palette.color(role)
        return float(colour.lightnessF()) < 0.5
    except Exception:
        return False


def resolve_theme(preference: str, palette: Any = None) -> str:
    """``"light"`` ou ``"dark"`` a partir da preferência do usuário e da paleta.

    ``preference`` é ``"auto"`` (segue o QGIS), ``"light"`` ou ``"dark"``;
    qualquer outro valor conta como ``"auto"``. Sem paleta, automático é claro.
    """
    pref = str(preference or THEME_AUTO).strip().lower()
    if pref in (THEME_LIGHT, THEME_DARK):
        return pref
    return THEME_DARK if palette is not None and is_dark_palette(palette) else THEME_LIGHT


def get_sigmai_stylesheet(scale: float = 1.0, dark: bool = False) -> str:
    """Folha de estilo com medidas proporcionais ao DPI e a paleta do tema."""
    p = DARK if dark else LIGHT
    # Os indicadores de rádio/caixa usam dois SVG do próprio plugin; o QSS
    # não aceita data: URI, então o caminho é o absoluto da pasta de ícones,
    # com barras normais também no Windows (o Qt as prefere em url()).
    icons = str(Path(__file__).resolve().parents[1] / "icons").replace("\\", "/")

    def px(value: float) -> str:
        return f"{max(1, int(round(value * scale)))}px"

    # A folha é aplicada no próprio painel (panel.setStyleSheet), então cada
    # regra já vale só para a árvore do painel e ganha, por proximidade, de
    # qualquer regra do tema do aplicativo — sem precisar de prefixo de
    # descendência, que só inflaria a especificidade e faria "QLabel"
    # genérico vencer "QLabel#helpText".
    return f"""
    QWidget#sigmaiRoot {{
        background-color: {p.canvas};
        color: {p.ink};
        font-family: "Segoe UI", "Inter", "Noto Sans", Arial, sans-serif;
        font-size: {px(13)};
    }}
    /* Páginas dentro das abas e o viewport das áreas de rolagem: sem isto o
       fundo vinha do tema do QGIS, e ficava preto atrás dos cartões brancos. */
    QScrollArea, QScrollArea > QWidget > QWidget {{
        background-color: {p.canvas};
    }}
    QWidget#tabPage {{ background-color: {p.canvas}; }}
    /* Contêineres de linha (spinbox + barra, token + botões, aparência): sem
       isto o tema do QGIS pintava uma faixa cinza atrás deles. */
    QWidget#transparentRow {{ background: transparent; }}
    QToolTip {{ background-color: {p.surface}; color: {p.ink}; border: {px(1)} solid {p.line}; padding: {px(4)}; }}

    /* Todo texto solto — rótulos de formulário, rádios, caixas de seleção —
       tem cor e fundo declarados aqui, para não herdar o tema do aplicativo. */
    QLabel {{ color: {p.ink}; background: transparent; }}
    QRadioButton, QCheckBox {{
        spacing: {px(8)}; color: {p.ink}; background: transparent; padding: {px(3)} 0;
    }}
    /* Indicadores desenhados pela folha, não pelo estilo do QGIS: no tema
       escuro o círculo do rádio sumia (contorno escuro sobre fundo escuro). */
    QRadioButton::indicator, QCheckBox::indicator {{
        width: {px(15)}; height: {px(15)};
        background-color: {p.surface}; border: {px(1)} solid {p.ink_soft};
    }}
    QRadioButton::indicator {{ border-radius: {px(8)}; }}
    QCheckBox::indicator {{ border-radius: {px(4)}; }}
    QRadioButton::indicator:hover, QCheckBox::indicator:hover {{ border-color: {p.brand_bright}; }}
    QRadioButton::indicator:checked {{
        background-color: {p.brand_bright}; border-color: {p.brand_bright}; image: url("{icons}/dot_white.svg");
    }}
    QCheckBox::indicator:checked {{
        background-color: {p.brand_bright}; border-color: {p.brand_bright}; image: url("{icons}/check_white.svg");
    }}
    QRadioButton::indicator:disabled, QCheckBox::indicator:disabled {{ border-color: {p.line}; background-color: {p.disabled_surface}; }}
    QRadioButton:disabled, QCheckBox:disabled {{ color: {p.ink_muted}; }}

    QFrame#headerFrame {{
        background-color: {p.brand_deep};
        border-radius: {px(14)};
    }}
    QLabel#brandTitle {{ color: #FFFFFF; font-size: {px(21)}; font-weight: 800; background: transparent; }}
    QLabel#brandSubtitle {{ color: {p.accent}; font-size: {px(12)}; font-weight: 600; background: transparent; }}
    QLabel#brandContext {{ color: {p.header_text}; font-size: {px(11)}; background: transparent; }}
    QLabel#logoPanel {{ background-color: #FFFFFF; border-radius: {px(10)}; padding: {px(6)}; }}

    QLabel#pillOnline {{
        background-color: #0B6E4F; color: #FFFFFF; border-radius: {px(11)};
        padding: {px(5)} {px(12)}; font-weight: 700; font-size: {px(12)};
    }}
    QLabel#pillOffline {{
        background-color: {p.pill_offline}; color: {p.pill_offline_text}; border-radius: {px(11)};
        padding: {px(5)} {px(12)}; font-weight: 700; font-size: {px(12)};
    }}
    /* Seletor de idioma no cabeçalho: compacto, sobre o azul-petróleo. */
    QComboBox#languageCombo {{
        background-color: rgba(255, 255, 255, 0.10); color: #FFFFFF;
        border: {px(1)} solid rgba(255, 255, 255, 0.28); border-radius: {px(8)};
        padding: {px(3)} {px(8)}; font-weight: 600; min-height: {px(20)};
    }}
    QComboBox#languageCombo:hover {{ border-color: {p.accent}; }}
    QComboBox#languageCombo::drop-down {{ border: none; width: {px(18)}; }}
    QComboBox#languageCombo QAbstractItemView {{
        background-color: {p.surface}; color: {p.ink}; border: {px(1)} solid {p.line};
        selection-background-color: {p.brand_bright}; selection-color: #FFFFFF; outline: none;
    }}

    QTabWidget::pane {{
        border: {px(1)} solid {p.line};
        border-radius: {px(12)};
        background-color: {p.surface};
        top: {px(-1)};
    }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        background: transparent;
        color: {p.ink_soft};
        /* O padding lateral precisa ser modesto: com valores altos o Qt calcula
           a largura da aba antes de aplicar a folha de estilo e acaba elidindo
           o texto ("Conexão" virava "Conexã"). O min-width dá a folga. */
        padding: {px(9)} {px(12)};
        min-width: {px(72)};
        margin-right: {px(3)};
        /* A borda existe em todos os estados, transparente quando não
           selecionada: assim o modelo de caixa não muda ao trocar de aba e o
           rótulo não é elidido só porque a aba ganhou uma borda. */
        border: {px(1)} solid transparent;
        border-top-left-radius: {px(10)};
        border-top-right-radius: {px(10)};
    }}
    QTabBar::tab:selected {{ background: {p.surface}; color: {p.brand}; border-color: {p.line}; border-bottom-color: {p.surface}; }}
    QTabBar::tab:hover:!selected {{ color: {p.ink}; }}
    /* Setas de rolagem das abas, para docks estreitos. */
    QTabBar QToolButton {{
        background-color: {p.surface}; border: {px(1)} solid {p.line}; border-radius: {px(6)}; color: {p.ink};
    }}
    QTabBar QToolButton:disabled {{ color: {p.ink_muted}; }}

    QFrame#stepCard {{
        background-color: {p.surface};
        border: {px(1)} solid {p.line};
        border-radius: {px(12)};
    }}
    QFrame#stepCardActive {{
        background-color: {p.surface};
        border: {px(2)} solid {p.brand_bright};
        border-radius: {px(12)};
    }}
    QLabel#stepNumber {{
        background-color: {p.brand_bright}; color: #FFFFFF;
        border-radius: {px(13)}; min-width: {px(26)}; max-width: {px(26)};
        min-height: {px(26)}; max-height: {px(26)};
        font-weight: 800; font-size: {px(13)};
    }}
    QLabel#stepNumberDone {{
        background-color: {p.line}; color: {p.ink_soft};
        border-radius: {px(13)}; min-width: {px(26)}; max-width: {px(26)};
        min-height: {px(26)}; max-height: {px(26)};
        font-weight: 800; font-size: {px(13)};
    }}
    QLabel#stepTitle {{ font-size: {px(14)}; font-weight: 700; color: {p.ink}; }}
    QLabel#stepHint {{ color: {p.ink_soft}; font-size: {px(12)}; }}
    QLabel#sectionTitle {{ font-size: {px(13)}; font-weight: 700; color: {p.brand}; }}
    QLabel#helpText {{ color: {p.ink_soft}; font-size: {px(12)}; }}
    QLabel#noticeOk {{ color: {p.ok}; font-size: {px(12)}; font-weight: 600; }}
    QLabel#noticeWarn {{
        color: {p.warn}; background-color: {p.warn_soft}; border: {px(1)} solid {p.warn_line};
        border-radius: {px(8)}; padding: {px(8)}; font-size: {px(12)};
    }}
    QLabel#noticeDanger {{
        color: {p.danger}; background-color: {p.danger_soft}; border: {px(1)} solid {p.danger_line};
        border-radius: {px(8)}; padding: {px(8)}; font-size: {px(12)}; font-weight: 600;
    }}

    QPushButton {{
        border-radius: {px(9)}; padding: {px(8)} {px(14)}; font-weight: 600;
        background-color: {p.surface}; color: {p.ink}; border: {px(1)} solid {p.line};
    }}
    QPushButton:hover {{ border-color: {p.brand_bright}; }}
    QPushButton:disabled {{ color: {p.ink_muted}; border-color: {p.line}; background-color: {p.disabled_surface}; }}
    QPushButton#primaryButton {{ background-color: {p.brand_bright}; color: #FFFFFF; border-color: {p.brand_bright}; }}
    QPushButton#primaryButton:hover {{ background-color: #0B6E4F; border-color: #0B6E4F; }}
    QPushButton#dangerButton {{ background-color: {p.danger_soft}; color: {p.danger}; border-color: {p.danger_line}; }}
    QPushButton#linkButton {{
        background: transparent; border: none; color: {p.brand}; text-decoration: underline;
        padding: {px(2)} {px(4)}; font-weight: 600;
    }}
    QPushButton#devButtonOff {{ background-color: {p.surface}; color: {p.danger}; border: {px(2)} solid {p.danger_line}; }}
    QPushButton#devButtonOn {{ background-color: #A3231F; color: #FFFFFF; border: {px(2)} solid #6E120F; }}

    QLineEdit, QPlainTextEdit, QTextEdit,
    QSpinBox, QComboBox, QListWidget,
    QTableWidget {{
        background-color: {p.surface}; border: {px(1)} solid {p.line};
        border-radius: {px(8)}; padding: {px(6)}; color: {p.ink};
        selection-background-color: {p.accent}; selection-color: {p.brand_deep};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
    QSpinBox:focus {{ border-color: {p.brand_bright}; }}
    QLineEdit:read-only {{ color: {p.ink}; }}
    QPlainTextEdit#codeBlock, QLineEdit#codeField {{
        font-family: Consolas, "JetBrains Mono", "DejaVu Sans Mono", monospace;
        font-size: {px(11)}; background-color: {p.field}; color: {p.ink};
        border-left: {px(3)} solid {p.brand_bright};
    }}
    QComboBox::drop-down {{ border: none; width: {px(22)}; }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface}; color: {p.ink}; border: {px(1)} solid {p.line};
        selection-background-color: {p.brand_bright}; selection-color: #FFFFFF; outline: none;
    }}
    QSpinBox {{ padding-right: {px(18)}; }}
    QSpinBox::up-button, QSpinBox::down-button {{
        width: {px(16)}; background-color: {p.canvas}; border-left: {px(1)} solid {p.line};
    }}
    QSpinBox::up-button {{ border-top-right-radius: {px(8)}; }}
    QSpinBox::down-button {{ border-bottom-right-radius: {px(8)}; }}
    QListWidget::item {{ color: {p.ink}; padding: {px(2)}; }}
    QListWidget::item:selected {{ background-color: {p.brand_bright}; color: #FFFFFF; }}
    QTableWidget {{ gridline-color: {p.line}; alternate-background-color: {p.canvas}; }}
    QTableWidget::item {{ color: {p.ink}; padding: {px(2)} {px(4)}; }}
    QTableWidget::item:selected {{ background-color: {p.brand_bright}; color: #FFFFFF; }}
    QHeaderView::section {{
        background-color: {p.canvas}; color: {p.ink_soft}; border: none;
        border-bottom: {px(1)} solid {p.line}; padding: {px(6)}; font-weight: 700;
    }}
    QTableCornerButton::section {{ background-color: {p.canvas}; border: none; }}
    QProgressBar {{
        border: {px(1)} solid {p.line}; border-radius: {px(7)}; background: {p.canvas};
        text-align: center; color: {p.ink}; font-size: {px(11)}; height: {px(15)};
    }}
    QProgressBar::chunk {{ background-color: {p.brand_bright}; border-radius: {px(6)}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QGroupBox {{
        border: {px(1)} solid {p.line}; border-radius: {px(10)}; margin-top: {px(12)};
        padding-top: {px(10)}; font-weight: 700; background-color: {p.surface}; color: {p.ink};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; left: {px(12)}; padding: 0 {px(6)};
        color: {p.brand}; background-color: {p.canvas};
    }}

    /* Barras de rolagem: as do tema do QGIS destoavam dentro do painel. */
    QScrollBar:vertical {{
        background: {p.canvas}; width: {px(10)}; margin: 0; border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {p.scrollbar}; min-height: {px(24)}; border-radius: {px(5)};
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.brand_bright}; }}
    QScrollBar:horizontal {{
        background: {p.canvas}; height: {px(10)}; margin: 0; border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {p.scrollbar}; min-width: {px(24)}; border-radius: {px(5)};
    }}
    QScrollBar::handle:horizontal:hover {{ background: {p.brand_bright}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0; height: 0; border: none; background: none;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    """
