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
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from backend.state import AppState
from backend_api.api_client import APIClient
from UI.upload_window import ModelCheckWindow


class LoginThread(QThread):
    """Background thread for API login to avoid UI freezing"""
    finished = pyqtSignal(dict)

    def __init__(self, api_client, email, password):
        super().__init__()
        self.api_client = api_client
        self.email = email
        self.password = password

    def run(self):
        result = self.api_client.login(self.email, self.password)
        self.finished.emit(result)


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Inloggen")
        self.setMinimumSize(1100, 720)
        self._center_on_screen()

        # Initialize API client
        self.api_client = APIClient()
        self.login_thread = None

        self._build_ui()
        self._apply_styles()
        self._wire_events()
        self._check_backend_availability()

    def _check_backend_availability(self):
        """Check if backend is running"""
        if not self.api_client.health_check():
            QMessageBox.warning(
                self,
                "Backend niet beschikbaar",
                "Kan geen verbinding maken met de backend server.\n\n"
                "Zorg ervoor dat de server draait:\n"
                "cd backend_api\n"
                "python -m uvicorn main:app --reload"
            )

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

        # Links
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
        btn.clicked.connect(self._on_nav_clicked)
        return btn

    def _apply_styles(self):
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
                padding: 11px 11px;
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

            QPushButton#loginButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

    def _wire_events(self):
        self.email_input.returnPressed.connect(self._focus_password)
        self.password_input.returnPressed.connect(self.login_button.click)
        self.login_button.clicked.connect(self.handle_login)
        self.signup_link.linkActivated.connect(self._on_link_activated)
        self.reset_link.linkActivated.connect(self._on_link_activated)

    def _focus_password(self):
        self.password_input.setFocus()
        self.password_input.selectAll()

    def _on_link_activated(self, href: str):
        """Handle registration and password reset links"""
        if href == "create_account":
            # Auto-register with current email/password
            self._try_register()
        elif href == "reset_password":
            QMessageBox.information(
                self,
                "Binnenkort beschikbaar",
                "Wachtwoord reset functie wordt binnenkort toegevoegd."
        )

    def _on_nav_clicked(self):
        # Navigation functionality not implemented yet
        return

    def handle_login(self):
        """Handle login with backend authentication"""
        email = self.email_input.text().strip()
        password = self.password_input.text()

        # Validation
        if not email or not password:
            QMessageBox.warning(self, "Fout", "Voer zowel e-mailadres als wachtwoord in.")
            return

        if len(password) < 8:
            QMessageBox.warning(self, "Fout", "Wachtwoord moet minimaal 8 tekens bevatten.")
            return

        # Disable button during login
        self.login_button.setEnabled(False)
        self.login_button.setText("Inloggen...")

        # Start login in background thread
        self.login_thread = LoginThread(self.api_client, email, password)
        self.login_thread.finished.connect(self._on_login_complete)
        self.login_thread.start()

    def _on_login_complete(self, result: dict):
        """Handle login result"""
        self.login_button.setEnabled(True)
        self.login_button.setText("Login")

        if result["success"]:
            # Login successful - get user info
            user_info = self.api_client.get_user_info()

            if user_info:
                # Create app state with user data
                state = AppState()
                state.user.email = user_info["email"]

                # Show success message with trial info
                user_status = self.api_client.get_user_status()
                if user_status and user_status["is_trial"]:
                    QMessageBox.information(
                        self,
                        "Welkom!",
                        f"Welkom, {user_info['email']}!\n\n"
                        f"Je hebt een gratis proefperiode van 7 dagen.\n"
                        f"Trial verloopt op: {user_status['trial_ends_at'][:10]}"
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Welkom!",
                        f"Welkom terug, {user_info['email']}!\n\n"
                        f"Documenten beschikbaar: {user_status.get('documents_remaining', 0) if user_status else 0}"
                    )

                # Open next window
                self.close()
                self.model_window = ModelCheckWindow(state=state, api_client=self.api_client)
                self.model_window.show()
            else:
                QMessageBox.critical(
                    self,
                    "Fout",
                    "Kon gebruikersgegevens niet ophalen."
                )
        else:
            # Login failed
            error_message = result["error"]
            if "Incorrect email or password" in error_message:
                QMessageBox.warning(
                    self,
                    "Inloggen mislukt",
                    "Onjuist e-mailadres of wachtwoord.\n\n"
                    "Probeer het opnieuw of maak een nieuw account aan."
                )
            elif "not found" in error_message.lower():
                # User not found - offer to register
                reply = QMessageBox.question(
                    self,
                    "Account niet gevonden",
                    f"Geen account gevonden voor {self.email_input.text()}.\n\n"
                    "Wilt u een nieuw account aanmaken?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._try_register()
            else:
                QMessageBox.critical(
                    self,
                    "Verbindingsfout",
                    f"Kan geen verbinding maken met de server.\n\n"
                    f"Fout: {error_message}"
                )

    def _try_register(self):
        """Try to register user with current credentials"""
        email = self.email_input.text().strip()
        password = self.password_input.text()

        self.login_button.setEnabled(False)
        self.login_button.setText("Registreren...")

        result = self.api_client.register(email, password)

        self.login_button.setEnabled(True)
        self.login_button.setText("Login")

        if result["success"]:
            QMessageBox.information(
                self,
                "Account aangemaakt!",
                f"Account succesvol aangemaakt voor {email}!\n\n"
                "Je krijgt 7 dagen gratis proefperiode.\n\n"
                "Je wordt nu automatisch ingelogd..."
            )
            # Auto-login after registration
            self._on_login_complete(result)
        else:
            QMessageBox.critical(
                self,
                "Registratie mislukt",
                f"Kon account niet aanmaken.\n\n{result['error']}"
            )

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