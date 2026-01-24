import sys
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QToolButton,
    QMessageBox,
    QSizePolicy,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from backend.state import AppState
from UI.upload_window import ModelCheckWindow


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Inloggen")
        self.setMinimumSize(1100, 720)
        self._center_on_screen()

        self._build_ui()
        self._apply_styles()
        self._wire_events()

    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header (top navigation)
        self.header = QFrame()
        self.header.setObjectName("header")
        self.header.setFixedHeight(72)

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(26, 12, 26, 12)
        header_layout.setSpacing(14)

        # Logo placeholder (text-based, no image yet)
        self.logo = QLabel("ProJustitia.ai")
        self.logo.setObjectName("logo")
        self.logo.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.logo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        header_layout.addWidget(self.logo)
        header_layout.addStretch(1)

        # Navigation items (no functionality yet)
        nav_items = ["Home", "Diensten", "Veiligheid", "Gratis proberen", "FAQ", "Inloggen"]
        self.nav_buttons = []

        for i, text in enumerate(nav_items):
            btn = self._make_nav_button(text, selected=(text == "Inloggen"))
            self.nav_buttons.append(btn)
            header_layout.addWidget(btn)

            if i != len(nav_items) - 1:
                sep = QFrame()
                sep.setObjectName("navSep")
                sep.setFrameShape(QFrame.VLine)
                sep.setFrameShadow(QFrame.Plain)
                header_layout.addWidget(sep)

        root.addWidget(self.header)

        # Body wrapper
        self.body = QFrame()
        self.body.setObjectName("body")

        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # White page panel (like the website page area)
        self.page = QFrame()
        self.page.setObjectName("page")

        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(80, 64, 80, 64)
        page_layout.setSpacing(18)

        # Title
        self.title = QLabel("INLOGGEN")
        self.title.setObjectName("title")
        self.title.setFont(QFont("Segoe UI", 40, QFont.Bold))
        self.title.setAlignment(Qt.AlignLeft)

        page_layout.addWidget(self.title)
        page_layout.addSpacing(6)

        # Form container (kept simple, aligned left, like screenshot)
        form_wrap = QFrame()
        form_wrap.setObjectName("formWrap")
        form_layout = QVBoxLayout(form_wrap)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        # Email
        self.email_label = QLabel("E-mailadres*")
        self.email_label.setObjectName("fieldLabel")
        form_layout.addWidget(self.email_label)

        self.email_input = QLineEdit()
        self.email_input.setObjectName("input")
        self.email_input.setPlaceholderText("naam@bedrijf.nl")
        self.email_input.setFixedWidth(650)
        form_layout.addWidget(self.email_input)

        form_layout.addSpacing(10)

        # Password
        self.password_label = QLabel("Wachtwoord*")
        self.password_label.setObjectName("fieldLabel")
        form_layout.addWidget(self.password_label)

        self.password_input = QLineEdit()
        self.password_input.setObjectName("input")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFixedWidth(650)
        form_layout.addWidget(self.password_input)

        form_layout.addSpacing(14)

        # Links (no functionality yet)
        self.signup_link = QLabel(
            'Nog geen account? <a href="create_account">Klik hier</a> om een account aan te maken'
        )
        self.signup_link.setObjectName("linkLabel")
        self.signup_link.setTextFormat(Qt.RichText)
        self.signup_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.signup_link.setOpenExternalLinks(False)
        form_layout.addWidget(self.signup_link)

        self.reset_link = QLabel(
            'Wachtwoord vergeten? <a href="reset_password">Klik hier</a> om het opnieuw in te stellen'
        )
        self.reset_link.setObjectName("linkLabel")
        self.reset_link.setTextFormat(Qt.RichText)
        self.reset_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.reset_link.setOpenExternalLinks(False)
        form_layout.addWidget(self.reset_link)

        form_layout.addSpacing(18)

        # Login button (gold accent)
        self.login_button = QPushButton("Login")
        self.login_button.setObjectName("loginButton")
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.setFixedWidth(160)
        self.login_button.setFixedHeight(44)
        form_layout.addWidget(self.login_button, alignment=Qt.AlignLeft)

        page_layout.addWidget(form_wrap, alignment=Qt.AlignLeft)
        page_layout.addStretch(1)

        body_layout.addWidget(self.page)
        root.addWidget(self.body)

        self.setLayout(root)

    def _make_nav_button(self, text: str, selected: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setAutoRaise(True)
        btn.setObjectName("navButtonSelected" if selected else "navButton")
        btn.clicked.connect(self._on_nav_clicked)  # no functionality yet
        return btn

    def _apply_styles(self):
        # Palette from user:
        # Primary blue: rgb(0, 51, 102)
        # Neutral background: rgb(240, 240, 240)
        # Accent gold: #ffd700
        # Text: rgb(50, 50, 50)
        # White: rgb(255, 255, 255)

        self.setStyleSheet("""
            QWidget {
                background-color: rgb(240, 240, 240);
                color: rgb(50, 50, 50);
                font-family: "Segoe UI";
            }

            /* Header */
            QFrame#header {
                background-color: rgb(255, 255, 255);
                border-bottom: 1px solid rgba(0, 0, 0, 18);
            }

            QLabel#logo {
                color: rgb(0, 51, 102);
                background: transparent;
            }

            QFrame#navSep {
                color: rgba(0, 0, 0, 25);
            }

            QToolButton#navButton {
                background: transparent;
                color: rgb(0, 51, 102);
                border: none;
                padding: 6px 8px;
                font-size: 14px;
                font-weight: 500;
            }

            QToolButton#navButton:hover {
                color: rgb(0, 38, 77);
                text-decoration: underline;
            }

            QToolButton#navButtonSelected {
                background: transparent;
                color: rgb(0, 51, 102);
                border: none;
                padding: 6px 8px;
                font-size: 14px;
                font-weight: 700;
                text-decoration: underline;
            }

            /* Body page */
            QFrame#body {
                background-color: rgb(240, 240, 240);
            }

            QFrame#page {
                background-color: rgb(255, 255, 255);
                border: 1px solid rgba(0, 0, 0, 10);
                border-radius: 12px;
                margin: 22px 26px 26px 26px;
            }

            QLabel#title {
                color: rgb(0, 51, 102);
                background: transparent;
                letter-spacing: 1px;
            }

            QLabel#fieldLabel {
                color: rgb(50, 50, 50);
                background: transparent;
                font-size: 14px;
                font-weight: 600;
            }

            QLineEdit#input {
                background-color: rgb(255, 255, 255);
                color: rgb(50, 50, 50);
                border: 1px solid rgba(0, 0, 0, 18);
                border-radius: 10px;
                padding: 12px 12px;
                font-size: 14px;
            }

            QLineEdit#input:focus {
                border: 2px solid #ffd700;
                padding: 11px 11px; /* keep size stable with thicker border */
            }

            QLabel#linkLabel {
                color: rgb(50, 50, 50);
                background: transparent;
                font-size: 13px;
            }

            QLabel#linkLabel a {
                color: rgb(0, 51, 102);
                font-weight: 700;
                text-decoration: none;
            }

            QLabel#linkLabel a:hover {
                text-decoration: underline;
            }

            QPushButton#loginButton {
                background-color: #ffd700;
                color: rgb(0, 51, 102);
                border: 1px solid rgba(0, 0, 0, 10);
                border-radius: 10px;
                font-size: 14px;
                font-weight: 800;
            }

            QPushButton#loginButton:hover {
                background-color: #ffdf33;
            }

            QPushButton#loginButton:pressed {
                background-color: #e6c200;
            }
        """)

    def _wire_events(self):
        # Enter on email moves focus to password
        self.email_input.returnPressed.connect(self._focus_password)

        # Enter on password triggers login (convenient, not required but useful)
        self.password_input.returnPressed.connect(self.login_button.click)

        self.login_button.clicked.connect(self.handle_login)

        # Links: no functionality yet
        self.signup_link.linkActivated.connect(self._on_link_activated)
        self.reset_link.linkActivated.connect(self._on_link_activated)

    def _focus_password(self):
        self.password_input.setFocus()
        self.password_input.selectAll()

    def _on_link_activated(self, _href: str):
        # No functionality yet
        return

    def _on_nav_clicked(self):
        # No functionality yet
        return

    def handle_login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email or not password:
            QMessageBox.warning(self, "Fout", "Voer zowel e-mailadres als wachtwoord in.")
            return

    # Create app state and store user context
        state = AppState()
        state.user.email = email

        self.close()
        self.model_window = ModelCheckWindow(state=state)
        self.model_window.show()


    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        rect = screen.availableGeometry()
        x = rect.x() + (rect.width() - self.width()) // 2
        y = rect.y() + (rect.height() - self.height()) // 2
        self.move(x, y)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec_())
