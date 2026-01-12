from __future__ import annotations

from PyQt5.QtWidgets import QApplication, QWidget


# Color palette (requested)
PRIMARY_BLUE = "rgb(0, 51, 102)"
BG_NEUTRAL = "rgb(240, 240, 240)"
ACCENT_GOLD = "#FFA500"
TEXT_DARK = "rgb(50, 50, 50)"
WHITE = "rgb(255, 255, 255)"


def get_app_stylesheet() -> str:
    """
    Global QSS theme for the application.
    Use object names where you want a "page" / "card" layout:
      - QFrame with objectName "page"
      - QFrame with objectName "card"
      - QLabel with objectName "title"
      - QLabel with objectName "sectionTitle"
      - QLabel with objectName "fieldLabel"
      - QLineEdit with objectName "input"
      - QPushButton with objectName "primaryButton"
    """
    return f"""
        /* Base */
        QWidget {{
            background-color: {BG_NEUTRAL};
            color: {TEXT_DARK};
            font-family: "Segoe UI";
        }}

        /* Generic containers */
        QFrame#page {{
            background-color: {WHITE};
            border: 1px solid rgba(0, 0, 0, 10);
            border-radius: 12px;
        }}

        QFrame#card {{
            background-color: {WHITE};
            border: 1px solid rgba(0, 0, 0, 12);
            border-radius: 14px;
        }}

        /* Titles */
        QLabel#title {{
            color: {PRIMARY_BLUE};
            background: transparent;
            letter-spacing: 1px;
            font-weight: 800;
        }}

        QLabel#sectionTitle {{
            color: {PRIMARY_BLUE};
            background: transparent;
            font-weight: 700;
        }}

        QLabel#fieldLabel {{
            color: {TEXT_DARK};
            background: transparent;
            font-weight: 600;
        }}

        /* Inputs */
        QLineEdit#input, QTextEdit#input, QPlainTextEdit#input {{
            background-color: {WHITE};
            color: {TEXT_DARK};
            border: 1px solid rgba(0, 0, 0, 18);
            border-radius: 10px;
            padding: 10px 12px;
            font-size: 14px;
        }}

        QLineEdit#input:focus, QTextEdit#input:focus, QPlainTextEdit#input:focus {{
            border: 2px solid {ACCENT_GOLD};
            padding: 9px 11px; /* keep size stable with thicker border */
        }}

        /* Buttons */
        QPushButton#primaryButton {{
            background-color: {ACCENT_GOLD};
            color: {PRIMARY_BLUE};
            border: 1px solid rgba(0, 0, 0, 10);
            border-radius: 10px;
            padding: 10px 14px;
            font-size: 14px;
            font-weight: 800;
        }}

        QPushButton#primaryButton:hover {{
            background-color: #ffdf33;
        }}

        QPushButton#primaryButton:pressed {{
            background-color: #e6c200;
        }}

        QPushButton#secondaryButton {{
            background-color: {WHITE};
            color: {PRIMARY_BLUE};
            border: 1px solid rgba(0, 51, 102, 40);
            border-radius: 10px;
            padding: 10px 14px;
            font-size: 14px;
            font-weight: 700;
        }}

        QPushButton#secondaryButton:hover {{
            border: 1px solid rgba(0, 51, 102, 70);
            background-color: rgba(0, 51, 102, 4);
        }}

        /* Links */
        QLabel#linkLabel {{
            color: {TEXT_DARK};
            background: transparent;
        }}

        QLabel#linkLabel a {{
            color: {PRIMARY_BLUE};
            font-weight: 700;
            text-decoration: none;
        }}

        QLabel#linkLabel a:hover {{
            text-decoration: underline;
        }}

        /* Tables (for overview screens) */
        QTableWidget {{
            background-color: {WHITE};
            gridline-color: rgba(0, 0, 0, 12);
            border: 1px solid rgba(0, 0, 0, 10);
            border-radius: 10px;
        }}

        QHeaderView::section {{
            background-color: rgba(0, 51, 102, 6);
            color: {PRIMARY_BLUE};
            border: none;
            padding: 8px 10px;
            font-weight: 700;
        }}

        QTableWidget::item {{
            padding: 6px 8px;
        }}

        QTableWidget::item:selected {{
            background-color: rgba(255, 215, 0, 30);
            color: {TEXT_DARK};
        }}

        /* Lists */
        QListWidget {{
            background-color: {WHITE};
            border: 1px solid rgba(0, 0, 0, 10);
            border-radius: 10px;
        }}

        QListWidget::item {{
            padding: 8px 10px;
        }}

        QListWidget::item:selected {{
            background-color: rgba(255, 215, 0, 30);
            color: {TEXT_DARK};
        }}
    """


def apply_app_theme(app: QApplication) -> None:
    """
    Apply the stylesheet once for the whole application.
    Safe to call multiple times.
    """
    if app is None:
        return

    # Avoid reapplying if already set
    current = app.styleSheet() or ""
    new_sheet = get_app_stylesheet()

    if current.strip() != new_sheet.strip():
        app.setStyleSheet(new_sheet)


def apply_window_theme(window: QWidget) -> None:
    """
    Convenience helper: applies theme through QApplication instance.
    Call this in each window __init__ after UI is built.
    """
    app = QApplication.instance()
    if app is not None:
        apply_app_theme(app)
