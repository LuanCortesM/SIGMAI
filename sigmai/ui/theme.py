"""Folha de estilo do painel do SIGMAI.

Paleta derivada da identidade do plugin (verde-esmeralda sobre azul-petróleo),
com contraste verificado para texto: o cinza de apoio #5B6B77 sobre #FFFFFF
fica em 5.4:1, acima do mínimo 4.5:1 da WCAG AA para texto normal.
"""

from __future__ import annotations

INK = "#16232B"
INK_SOFT = "#5B6B77"
LINE = "#D6E0E6"
SURFACE = "#FFFFFF"
CANVAS = "#F4F7F9"
BRAND_DEEP = "#062A3A"
BRAND = "#0B6E4F"
BRAND_BRIGHT = "#00A86B"
ACCENT = "#20E39A"
DANGER = "#A3231F"
DANGER_SOFT = "#FDF3F2"
WARN = "#8A5A00"
WARN_SOFT = "#FFF8E8"


def get_sigmai_stylesheet(scale: float = 1.0) -> str:
    """Folha de estilo com medidas proporcionais ao DPI do sistema."""

    def px(value: float) -> str:
        return f"{max(1, int(round(value * scale)))}px"

    return f"""
    QWidget#sigmaiRoot, QDialog {{
        background-color: {CANVAS};
        color: {INK};
        font-family: "Segoe UI", "Inter", "Noto Sans", Arial, sans-serif;
        font-size: {px(13)};
    }}

    QFrame#headerFrame {{
        background-color: {BRAND_DEEP};
        border-radius: {px(14)};
    }}
    QLabel#brandTitle {{ color: #FFFFFF; font-size: {px(21)}; font-weight: 800; background: transparent; }}
    QLabel#brandSubtitle {{ color: {ACCENT}; font-size: {px(12)}; font-weight: 600; background: transparent; }}
    QLabel#brandContext {{ color: #C4D4DD; font-size: {px(11)}; background: transparent; }}
    QLabel#logoPanel {{ background-color: #FFFFFF; border-radius: {px(10)}; padding: {px(6)}; }}

    QLabel#pillOnline {{
        background-color: #0B6E4F; color: #FFFFFF; border-radius: {px(11)};
        padding: {px(5)} {px(12)}; font-weight: 700; font-size: {px(12)};
    }}
    QLabel#pillOffline {{
        background-color: #33454F; color: #C4D4DD; border-radius: {px(11)};
        padding: {px(5)} {px(12)}; font-weight: 700; font-size: {px(12)};
    }}

    QTabWidget::pane {{
        border: {px(1)} solid {LINE};
        border-radius: {px(12)};
        background-color: {SURFACE};
        top: {px(-1)};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {INK_SOFT};
        /* O padding lateral precisa ser modesto: com valores altos o Qt calcula
           a largura da aba antes de aplicar a folha de estilo e acaba elidindo
           o texto ("Conexão" virava "Conexã"). O min-width dá a folga. */
        padding: {px(9)} {px(14)};
        min-width: {px(96)};
        margin-right: {px(3)};
        /* A borda existe em todos os estados, transparente quando não
           selecionada: assim o modelo de caixa não muda ao trocar de aba e o
           rótulo não é elidido só porque a aba ganhou uma borda. */
        border: {px(1)} solid transparent;
        border-top-left-radius: {px(10)};
        border-top-right-radius: {px(10)};
        font-weight: 600;
    }}
    QTabBar::tab:selected {{ background: {SURFACE}; color: {BRAND}; border-color: {LINE}; border-bottom-color: {SURFACE}; }}
    QTabBar::tab:hover:!selected {{ color: {INK}; }}

    QFrame#stepCard {{
        background-color: {SURFACE};
        border: {px(1)} solid {LINE};
        border-radius: {px(12)};
    }}
    QFrame#stepCardActive {{
        background-color: {SURFACE};
        border: {px(2)} solid {BRAND_BRIGHT};
        border-radius: {px(12)};
    }}
    QLabel#stepNumber {{
        background-color: {BRAND_BRIGHT}; color: #FFFFFF;
        border-radius: {px(13)}; min-width: {px(26)}; max-width: {px(26)};
        min-height: {px(26)}; max-height: {px(26)};
        font-weight: 800; font-size: {px(13)};
    }}
    QLabel#stepNumberDone {{
        background-color: {LINE}; color: {INK_SOFT};
        border-radius: {px(13)}; min-width: {px(26)}; max-width: {px(26)};
        min-height: {px(26)}; max-height: {px(26)};
        font-weight: 800; font-size: {px(13)};
    }}
    QLabel#stepTitle {{ font-size: {px(14)}; font-weight: 700; color: {INK}; }}
    QLabel#stepHint {{ color: {INK_SOFT}; font-size: {px(12)}; }}
    QLabel#sectionTitle {{ font-size: {px(13)}; font-weight: 700; color: {BRAND_DEEP}; }}
    QLabel#helpText {{ color: {INK_SOFT}; font-size: {px(12)}; }}
    QLabel#noticeOk {{ color: #0B6E4F; font-size: {px(12)}; font-weight: 600; }}
    QLabel#noticeWarn {{
        color: {WARN}; background-color: {WARN_SOFT}; border: {px(1)} solid #F0D9A8;
        border-radius: {px(8)}; padding: {px(8)}; font-size: {px(12)};
    }}
    QLabel#noticeDanger {{
        color: {DANGER}; background-color: {DANGER_SOFT}; border: {px(1)} solid #F0C4C2;
        border-radius: {px(8)}; padding: {px(8)}; font-size: {px(12)}; font-weight: 600;
    }}

    QPushButton {{
        border-radius: {px(9)}; padding: {px(8)} {px(14)}; font-weight: 600;
        background-color: {SURFACE}; color: {BRAND_DEEP}; border: {px(1)} solid {LINE};
    }}
    QPushButton:hover {{ border-color: {BRAND_BRIGHT}; }}
    QPushButton:disabled {{ color: #9AAAB4; border-color: #E6EDF1; background-color: #FAFCFD; }}
    QPushButton#primaryButton {{ background-color: {BRAND_BRIGHT}; color: #FFFFFF; border-color: {BRAND_BRIGHT}; }}
    QPushButton#primaryButton:hover {{ background-color: {BRAND}; border-color: {BRAND}; }}
    QPushButton#dangerButton {{ background-color: {DANGER_SOFT}; color: {DANGER}; border-color: #F0C4C2; }}
    QPushButton#linkButton {{
        background: transparent; border: none; color: {BRAND}; text-decoration: underline;
        padding: {px(2)} {px(4)}; font-weight: 600;
    }}
    QPushButton#devButtonOff {{ background-color: {SURFACE}; color: {DANGER}; border: {px(2)} solid #F0C4C2; }}
    QPushButton#devButtonOn {{ background-color: {DANGER}; color: #FFFFFF; border: {px(2)} solid #6E120F; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QListWidget, QTableWidget {{
        background-color: {SURFACE}; border: {px(1)} solid {LINE};
        border-radius: {px(8)}; padding: {px(6)}; color: {INK};
        selection-background-color: {ACCENT}; selection-color: {BRAND_DEEP};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {BRAND_BRIGHT}; }}
    QPlainTextEdit#codeBlock, QLineEdit#codeField {{
        font-family: Consolas, "JetBrains Mono", "DejaVu Sans Mono", monospace;
        font-size: {px(11)}; background-color: #F7FAFB; color: {BRAND_DEEP};
        border-left: {px(3)} solid {BRAND_BRIGHT};
    }}
    QHeaderView::section {{
        background-color: {CANVAS}; color: {INK_SOFT}; border: none;
        border-bottom: {px(1)} solid {LINE}; padding: {px(6)}; font-weight: 700;
    }}
    QTableWidget {{ gridline-color: #EAF0F3; }}
    QRadioButton, QCheckBox {{ spacing: {px(8)}; color: {INK}; padding: {px(3)} 0; }}
    QRadioButton::indicator, QCheckBox::indicator {{ width: {px(15)}; height: {px(15)}; }}
    QProgressBar {{
        border: {px(1)} solid {LINE}; border-radius: {px(7)}; background: {CANVAS};
        text-align: center; color: {INK_SOFT}; font-size: {px(11)}; height: {px(15)};
    }}
    QProgressBar::chunk {{ background-color: {BRAND_BRIGHT}; border-radius: {px(6)}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QGroupBox {{
        border: {px(1)} solid {LINE}; border-radius: {px(10)}; margin-top: {px(12)};
        padding-top: {px(10)}; font-weight: 700; background-color: {SURFACE};
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: {px(12)}; padding: 0 {px(6)}; color: {BRAND}; }}
    """
