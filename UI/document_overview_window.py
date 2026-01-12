# UI/document_overview_window.py

import sys
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QHBoxLayout,
    QScrollArea,
    QLineEdit,
    QFormLayout,
    QApplication,
    QFrame,
    QSizePolicy,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from backend.config import OUTPUT_DIR
from UI.ui_theme import apply_window_theme


class DocumentOverviewWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Documentoverzicht")
        self.setMinimumSize(1100, 720)
        self._center_on_screen()

        self.document_widgets = []
        self._build_ui()
        self.load_documents()

        apply_window_theme(self)

    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(26, 22, 26, 26)
        wrapper.setSpacing(0)

        self.page = QFrame()
        self.page.setObjectName("page")

        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(80, 64, 80, 64)
        page_layout.setSpacing(16)

        title = QLabel("Documentoverzicht en workflow selectie")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 30, QFont.Bold))
        title.setAlignment(Qt.AlignLeft)
        page_layout.addWidget(title)

        subtitle = QLabel("Controleer document types en kies de juiste workflow per document.")
        subtitle.setObjectName("fieldLabel")
        subtitle.setFont(QFont("Segoe UI", 12))
        page_layout.addWidget(subtitle)

        # Scroll area for document cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 10, 0, 10)
        self.scroll_layout.setSpacing(12)
        self.scroll_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.scroll_content)
        page_layout.addWidget(self.scroll_area, 1)

        # Buttons row
        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        self.create_btn = QPushButton("Dossier aanmaken")
        self.create_btn.setObjectName("primaryButton")
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.clicked.connect(self.go_next)

        self.cancel_btn = QPushButton("Annuleren")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.close)

        button_row.addWidget(self.create_btn, alignment=Qt.AlignLeft)
        button_row.addWidget(self.cancel_btn, alignment=Qt.AlignLeft)
        button_row.addStretch(1)

        page_layout.addLayout(button_row)

        wrapper.addWidget(self.page)
        container = QWidget()
        container.setLayout(wrapper)

        root.addWidget(container)
        self.setLayout(root)

    def _combo_style(self) -> str:
        # Matches the global palette (blue / light gray / gold / dark gray / white)
        return """
            QComboBox {
                background-color: rgb(255, 255, 255);
                color: rgb(50, 50, 50);
                border: 1px solid rgba(0, 0, 0, 18);
                border-radius: 10px;
                padding: 8px 10px;
                font-size: 14px;
            }
            QComboBox:focus {
                border: 2px solid #ffd700;
                padding: 7px 9px;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
        """

    def load_documents(self):
        # Clear existing widgets
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.document_widgets = []

        files = sorted(OUTPUT_DIR.glob("*_summary.txt"))

        if not files:
            empty = QLabel("Geen samenvattingen gevonden. Maak eerst een dossier aan via ZIP-upload.")
            empty.setObjectName("fieldLabel")
            empty.setFont(QFont("Segoe UI", 12))
            self.scroll_layout.addWidget(empty)
            self.create_btn.setEnabled(False)
            return

        self.create_btn.setEnabled(True)

        for file_path in files:
            filename = file_path.name

            card = QFrame()
            card.setObjectName("card")

            form = QFormLayout(card)
            form.setContentsMargins(18, 16, 18, 16)
            form.setHorizontalSpacing(18)
            form.setVerticalSpacing(10)

            name_field = QLineEdit(filename)
            name_field.setObjectName("input")
            name_field.setReadOnly(True)

            type_box = QComboBox()
            type_box.setStyleSheet(self._combo_style())
            type_box.addItems([
                "Oude PJ rapportage",
                "Reclasseringsrapport",
                "TLL rapport",
                "Observatieverslag",
                "Onbekend",
            ])

            workflow_box = QComboBox()
            workflow_box.setStyleSheet(self._combo_style())
            workflow_box.addItems([
                "Oude Pro Justitia (Oude PJ) rapportage Samenvatter 1.0 - Maart 2024",
                "Reclasseringsrapport Samenvatter 1.0 - Maart 2024",
                "TLL Generator (obv vordering IBS)",
                "Standaard Samenvatting",
            ])

            label_font = QFont("Segoe UI", 11)
            label_font.setBold(True)

            name_label = QLabel("Naam:")
            name_label.setObjectName("fieldLabel")
            name_label.setFont(label_font)

            type_label = QLabel("Document Type:")
            type_label.setObjectName("fieldLabel")
            type_label.setFont(label_font)

            workflow_label = QLabel("Workflow:")
            workflow_label.setObjectName("fieldLabel")
            workflow_label.setFont(label_font)

            form.addRow(name_label, name_field)
            form.addRow(type_label, type_box)
            form.addRow(workflow_label, workflow_box)

            self.scroll_layout.addWidget(card)

            self.document_widgets.append({
                "filename": filename,
                "type_box": type_box,
                "workflow_box": workflow_box,
            })

        self.scroll_layout.addStretch(1)

    def go_next(self):
        from UI.dossier_start_window import DossierStartWindow

        selected_docs = []
        for doc in self.document_widgets:
            selected_docs.append({
                "filename": doc["filename"],
                "doc_type": doc["type_box"].currentText(),
                "workflow": doc["workflow_box"].currentText(),
            })

        self.next_window = DossierStartWindow(documents=selected_docs)
        self.next_window.show()
        self.close()

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
    window = DocumentOverviewWindow()
    window.show()
    sys.exit(app.exec_())
