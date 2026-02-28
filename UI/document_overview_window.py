# UI/document_overview_window.py

import sys
from typing import Optional, List, Tuple

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
    QCheckBox,
    QMessageBox,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from backend.state import AppState, DocumentState
from UI.ui_theme import apply_window_theme


# (code, label)
DOC_TYPE_OPTIONS: List[Tuple[str, str]] = [
    ("PV", "Proces-verbaal"),
    ("VC", "Verhoor / VC"),
    ("RECLASS", "Reclasseringsrapport"),
    ("UJD", "UJD"),
    ("PJ", "Oude PJ rapportage"),
    ("TLL", "TLL rapport"),
    ("UNKNOWN", "Onbekend"),
]

class NoWheelComboBox(QComboBox):
    # All comments intentionally in English.
    def wheelEvent(self, event):
        # Ignore mouse wheel to prevent accidental value changes while scrolling.
        event.ignore()

class DocumentOverviewWindow(QWidget):
    """
    Documents Manager:
    - shows detected document types
    - allows override type + select documents
    - button "Archief (case) aanmaken" queues selected docs and navigates to summaries table
    """

    def __init__(self, state: Optional[AppState] = None):
        super().__init__()

        self.state = state
        self.setWindowTitle("Documenten beheren")
        self.setMinimumSize(1100, 720)
        self._center_on_screen()

        self.document_widgets = []
        self._build_ui()
        apply_window_theme(self)

        self.load_documents()

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

        title = QLabel("Documenten (types controleren & selecteren)")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 30, QFont.Bold))
        title.setAlignment(Qt.AlignLeft)
        page_layout.addWidget(title)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("fieldLabel")
        self.subtitle.setFont(QFont("Segoe UI", 12))
        page_layout.addWidget(self.subtitle)

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

        self.create_btn = QPushButton("Archief (case) aanmaken")
        self.create_btn.setObjectName("primaryButton")
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.clicked.connect(self.create_case_archive)

        self.back_btn = QPushButton("Terug")
        self.back_btn.setObjectName("secondaryButton")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.go_back)

        button_row.addWidget(self.create_btn, alignment=Qt.AlignLeft)
        button_row.addWidget(self.back_btn, alignment=Qt.AlignLeft)
        button_row.addStretch(1)

        page_layout.addLayout(button_row)

        wrapper.addWidget(self.page)
        container = QWidget()
        container.setLayout(wrapper)

        root.addWidget(container)
        self.setLayout(root)

    def _combo_style(self) -> str:
        # QComboBox is not styled in global theme, so we style it locally.
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
                border: 2px solid #FFA500;
                padding: 7px 9px;
            }
            QComboBox::drop-down {
                border: none;
                width: 34px;
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

        if self.state is None or not self.state.documents:
            self.subtitle.setText("Geen documenten beschikbaar. Upload eerst een ZIP-bestand.")
            empty = QLabel("Geen documenten gevonden.")
            empty.setObjectName("fieldLabel")
            empty.setFont(QFont("Segoe UI", 12))
            self.scroll_layout.addWidget(empty)
            self.create_btn.setEnabled(False)
            return

        self.create_btn.setEnabled(True)
        self.subtitle.setText(f"Case: {self.state.case.case_id} • Documenten: {len(self.state.documents)}")

        for doc in self.state.documents:
            self._add_document_card(doc)

        self.scroll_layout.addStretch(1)

    def _add_document_card(self, doc: DocumentState) -> None:
        card = QFrame()
        card.setObjectName("card")

        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

        label_font = QFont("Segoe UI", 11)
        label_font.setBold(True)

        name_label = QLabel("Naam:")
        name_label.setObjectName("fieldLabel")
        name_label.setFont(label_font)

        type_label = QLabel("Document Type:")
        type_label.setObjectName("fieldLabel")
        type_label.setFont(label_font)

        sel_label = QLabel("Selecteren:")
        sel_label.setObjectName("fieldLabel")
        sel_label.setFont(label_font)

        name_field = QLineEdit(doc.original_name)
        name_field.setObjectName("input")
        name_field.setReadOnly(True)

        # Dropdown for type (stores code in userData)
        type_box = NoWheelComboBox()
        type_box.setEditable(False)
        type_box.setStyleSheet(self._combo_style())

        detected_code = (doc.detected_type or "UNKNOWN").strip()
        override_code = (doc.type_override or "").strip()
        pre_code = override_code or detected_code

        # Add standard options
        for code, label in DOC_TYPE_OPTIONS:
            type_box.addItem(f"{code} — {label}", userData=code)

        # If detected code is not in standard list, add it on top
        codes = [type_box.itemData(i) for i in range(type_box.count())]
        if detected_code and detected_code not in codes:
            type_box.insertItem(0, detected_code, userData=detected_code)

        # Preselect
        idx = -1
        for i in range(type_box.count()):
            if type_box.itemData(i) == pre_code:
                idx = i
                break
        if idx >= 0:
            type_box.setCurrentIndex(idx)

        selected_cb = QCheckBox()
        selected_cb.setChecked(bool(doc.selected))

        form.addRow(sel_label, selected_cb)
        form.addRow(name_label, name_field)
        form.addRow(type_label, type_box)

        self.scroll_layout.addWidget(card)

        self.document_widgets.append({
            "doc_id": doc.doc_id,
            "selected_cb": selected_cb,
            "type_box": type_box,
        })

    def create_case_archive(self):
        if self.state is None:
            QMessageBox.warning(self, "Fout", "Geen AppState gevonden.")
            return

        # Apply UI selections to state
        id_to_doc = {d.doc_id: d for d in self.state.documents}

        selected_count = 0
        for w in self.document_widgets:
            doc = id_to_doc.get(w["doc_id"])
            if doc is None:
                continue

            is_selected = bool(w["selected_cb"].isChecked())
            doc.selected = is_selected
            if is_selected:
                selected_count += 1

            chosen_code = w["type_box"].currentData()
            if chosen_code is None:
                chosen_code = ""

            chosen_code = str(chosen_code).strip()
            detected_code = (doc.detected_type or "").strip()

            # Store override only if different from detected
            if chosen_code and chosen_code != detected_code:
                doc.type_override = chosen_code
            else:
                doc.type_override = ""

        if selected_count == 0:
            QMessageBox.warning(self, "Geen selectie", "Selecteer minstens één document.")
            return

        # Queue selected docs and persist manifest
        self.state.mark_archive_created_and_queue_selected()
        self.state.save_manifest()

        # Go to Summaries Table (auto-start summarization)
        from UI.dossier_documents_window import DossierDocumentsWindow

        self.close()
        self.next_window = DossierDocumentsWindow(state=self.state)
        self.next_window.show()

    def go_back(self):
        # Back to ZIP upload screen
        from UI.zip_upload_window import ZipUploadWindow

        self.close()
        self.prev = ZipUploadWindow(state=self.state)
        self.prev.show()

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
