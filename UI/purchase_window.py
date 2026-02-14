# UI/purchase_window.py
"""
Purchase window for buying document packages via Stripe.
Allows users to select and purchase document packages.
"""

import sys
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFrame, QMessageBox, QRadioButton, QButtonGroup
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from backend.state import AppState
from UI.ui_theme import apply_window_theme


class PurchaseWindow(QWidget):
    """Window for purchasing document packages"""

    def __init__(self, state: Optional[AppState] = None, api_client=None, parent_window=None):
        super().__init__()

        self.state = state or AppState()
        self.api_client = api_client
        self.parent_window = parent_window  # To refresh after purchase

        self.setWindowTitle("Documentenpakket kopen")
        self.setMinimumSize(800, 600)
        self._center_on_screen()

        self.selected_package = "package_10"  # Default selection

        self._build_ui()
        apply_window_theme(self)
        self._load_user_status()

    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)

        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(26, 22, 26, 26)

        self.page = QFrame()
        self.page.setObjectName("page")

        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(60, 40, 60, 44)
        page_layout.setSpacing(20)

        # Title
        title = QLabel("Documentenpakket kopen")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        page_layout.addWidget(title)

        # Current balance
        self.balance_label = QLabel("Huidig saldo: laden...")
        self.balance_label.setObjectName("fieldLabel")
        self.balance_label.setFont(QFont("Segoe UI", 14))
        page_layout.addWidget(self.balance_label)

        page_layout.addSpacing(10)

        # Package selection
        packages_label = QLabel("Kies een pakket:")
        packages_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        page_layout.addWidget(packages_label)

        # Radio buttons for packages
        self.package_group = QButtonGroup(self)

        # Package 10
        self.package_10_radio = self._create_package_option(
            "package_10",
            "10 Documenten",
            "€9,99",
            "Perfect voor kleine dossiers"
        )
        page_layout.addWidget(self.package_10_radio)

        # Package 50
        self.package_50_radio = self._create_package_option(
            "package_50",
            "50 Documenten",
            "€39,99",
            "Beste waarde - €0,80 per document"
        )
        page_layout.addWidget(self.package_50_radio)

        # Package 100
        self.package_100_radio = self._create_package_option(
            "package_100",
            "100 Documenten",
            "€69,99",
            "Voor grote volumes - €0,70 per document"
        )
        page_layout.addWidget(self.package_100_radio)

        page_layout.addStretch(1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.cancel_btn = QPushButton("Annuleren")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.close)

        self.purchase_btn = QPushButton("Doorgaan naar betaling")
        self.purchase_btn.setObjectName("primaryButton")
        self.purchase_btn.setCursor(Qt.PointingHandCursor)
        self.purchase_btn.clicked.connect(self._handle_purchase)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.purchase_btn)

        page_layout.addLayout(btn_row)

        wrapper.addWidget(self.page)
        container = QWidget()
        container.setLayout(wrapper)

        root.addWidget(container)
        self.setLayout(root)

    def _create_package_option(self, package_id: str, title: str, price: str, description: str) -> QFrame:
        """Create a package option card"""
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(80)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)

        # Radio button
        radio = QRadioButton()
        radio.setObjectName(package_id)
        radio.toggled.connect(lambda checked: self._on_package_selected(package_id) if checked else None)
        self.package_group.addButton(radio)

        if package_id == "package_10":
            radio.setChecked(True)

        card_layout.addWidget(radio)

        # Package info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        info_layout.addWidget(title_label)

        desc_label = QLabel(description)
        desc_label.setObjectName("fieldLabel")
        info_layout.addWidget(desc_label)

        card_layout.addLayout(info_layout)
        card_layout.addStretch(1)

        # Price
        price_label = QLabel(price)
        price_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        price_label.setStyleSheet("color: rgb(0, 51, 102);")
        card_layout.addWidget(price_label)

        return card

    def _on_package_selected(self, package_id: str):
        """Handle package selection"""
        self.selected_package = package_id

    def _load_user_status(self):
        """Load and display current user balance"""
        if not self.api_client:
            self.balance_label.setText("Huidig saldo: Onbekend (offline modus)")
            return

        try:
            status = self.api_client.get_user_status()
            if status:
                balance = status.get("documents_remaining", 0)
                self.balance_label.setText(f"Huidig saldo: {balance} documenten")
            else:
                self.balance_label.setText("Huidig saldo: Kon niet laden")
        except Exception as e:
            self.balance_label.setText(f"Fout bij laden saldo: {str(e)}")

    def _handle_purchase(self):
        """Handle purchase button click"""
        if not self.api_client:
            QMessageBox.warning(
                self,
                "Offline modus",
                "Aankopen zijn niet mogelijk in offline modus.\n"
                "Controleer je internetverbinding."
            )
            return

        # Show test payment instruction
        QMessageBox.information(
            self,
            "Test Betaling",
            f"Je hebt gekozen: {self.selected_package}\n\n"
            "In de volgende stap gebruik je Stripe test kaart:\n"
            "Nummer: 4242 4242 4242 4242\n"
            "Vervaldatum: elke datum in de toekomst\n"
            "CVC: elke 3 cijfers\n\n"
            "OPMERKING: Stripe payment window komt in volgende update."
        )

        # TODO: Open Stripe payment window (will implement next)
        # For now, simulate successful payment
        self._simulate_test_payment()

    def _simulate_test_payment(self):
        """Simulate a test payment (temporary - will be replaced with real Stripe)"""
        reply = QMessageBox.question(
            self,
            "Simuleer betaling",
            "Wil je een TEST betaling simuleren?\n\n"
            "(Dit voegt direct documenten toe aan je account)",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Create payment intent
        result = self.api_client.create_payment_intent(self.selected_package)

        if not result["success"]:
            QMessageBox.critical(
                self,
                "Fout",
                f"Kon betaling niet starten:\n\n{result['error']}"
            )
            return

        # In real implementation, user would pay via Stripe here
        # For now, we'll just confirm the payment immediately

        # Extract payment_intent_id from client_secret
        client_secret = result["client_secret"]
        payment_intent_id = client_secret.split("_secret_")[0]

        # Confirm payment (in real app, this happens after Stripe payment)
        confirm_result = self.api_client.confirm_payment(payment_intent_id)

        if confirm_result["success"]:
            docs_added = confirm_result.get("documents_added", 0)
            new_balance = confirm_result.get("new_balance", 0)

            QMessageBox.information(
                self,
                "Betaling geslaagd!",
                f"✓ Betaling voltooid!\n\n"
                f"Documenten toegevoegd: {docs_added}\n"
                f"Nieuw saldo: {new_balance} documenten"
            )

            # Refresh balance display
            self._load_user_status()

            # Close window and return to parent
            self.close()

        else:
            QMessageBox.critical(
                self,
                "Fout",
                f"Betaling bevestiging mislukt:\n\n{confirm_result['error']}"
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
    window = PurchaseWindow()
    window.show()
    sys.exit(app.exec_())