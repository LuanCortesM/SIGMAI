from __future__ import annotations


def get_sigmai_stylesheet() -> str:
    return """
    QDialog {
        background-color: #F6F8FA;
        color: #1E2A32;
        font-family: "Segoe UI", "Inter", Arial, sans-serif;
        font-size: 13px;
    }
    QLabel#brandTitle {
        color: #FFFFFF;
        font-size: 28px;
        font-weight: 800;
        background: transparent;
    }
    QLabel#brandSubtitle {
        color: #20E39A;
        font-size: 13px;
        font-weight: 600;
        background: transparent;
    }
    QLabel#brandContext {
        color: #D8E1E8;
        font-size: 11px;
        background: transparent;
    }
    QLabel#logoPanel {
        background-color: #FFFFFF;
        border: 1px solid #D8E1E8;
        border-radius: 12px;
        padding: 8px;
    }
    QLabel#statusBadgeOnline {
        background-color: #DDF8EC;
        color: #006B45;
        border: 1px solid #20E39A;
        border-radius: 10px;
        padding: 5px 10px;
        font-weight: 700;
    }
    QLabel#statusBadgeOffline {
        background-color: #EEF2F5;
        color: #6B7A86;
        border: 1px solid #D8E1E8;
        border-radius: 10px;
        padding: 5px 10px;
        font-weight: 700;
    }
    QFrame#headerFrame {
        background-color: #062A3A;
        border: 1px solid #075D68;
        border-radius: 16px;
    }
    QLabel#sectionHint {
        color: #6B7A86;
        font-size: 12px;
        font-weight: 500;
    }
    QLabel#dangerText {
        color: #8A1F1F;
        font-size: 12px;
        font-weight: 600;
        background-color: #FFF5F5;
        border: 1px solid #F0B8B8;
        border-radius: 8px;
        padding: 8px;
    }
    QLabel#devBadgeOff {
        background-color: #EEF2F5;
        color: #6B7A86;
        border: 1px solid #D8E1E8;
        border-radius: 10px;
        padding: 5px 10px;
        font-weight: 800;
    }
    QLabel#devBadgeOn {
        background-color: #B42323;
        color: #FFFFFF;
        border: 1px solid #7A1010;
        border-radius: 10px;
        padding: 5px 10px;
        font-weight: 900;
    }
    QGroupBox {
        background-color: #FFFFFF;
        border: 1px solid #BFD8DE;
        border-radius: 14px;
        margin-top: 12px;
        padding: 12px;
        font-weight: 700;
        color: #1E2A32;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: #075D68;
        background-color: #FFFFFF;
    }
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #FFFFFF;
        border: 1px solid #D8E1E8;
        border-radius: 10px;
        padding: 7px;
        color: #1E2A32;
    }
    QLineEdit[technical="true"], QTextEdit[technical="true"] {
        font-family: Consolas, "JetBrains Mono", monospace;
        color: #062A3A;
        background-color: #F6F8FA;
        border-left: 3px solid #00A86B;
    }
    QPushButton {
        border-radius: 10px;
        padding: 8px 12px;
        font-weight: 700;
        background-color: #FFFFFF;
        color: #075D68;
        border: 1px solid #D8E1E8;
    }
    QPushButton:hover {
        background-color: #EEF8F5;
        border: 1px solid #00A86B;
    }
    QPushButton#primaryButton {
        background-color: #00A86B;
        color: #FFFFFF;
        border: 1px solid #00A86B;
    }
    QPushButton#secondaryButton {
        background-color: #FFFFFF;
        color: #075D68;
        border: 1px solid #BFD8DE;
    }
    QPushButton#languageButton {
        background-color: #FFFFFF;
        color: #062A3A;
        border: 1px solid #20E39A;
        border-radius: 10px;
        padding: 6px 10px;
        font-weight: 900;
        min-width: 58px;
    }
    QPushButton#languageButton:hover {
        background-color: #DDF8EC;
        border: 1px solid #20E39A;
    }
    QPushButton#dangerButton {
        background-color: #FFF5F5;
        color: #B42323;
        border: 1px solid #F0B8B8;
    }
    QPushButton#devDangerButtonOff {
        background-color: #B42323;
        color: #FFFFFF;
        border: 2px solid #7A1010;
    }
    QPushButton#devDangerButtonOn {
        background-color: #7A1010;
        color: #FFFFFF;
        border: 2px solid #3F0505;
    }
    QCheckBox {
        spacing: 8px;
        color: #1E2A32;
    }
    """
