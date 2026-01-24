# UI/cases_list_window.py

import sys
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QFrame,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from backend.state import AppState, default_cases_root, DOC_STATUS_SUMMARIZED, DOC_STATUS_ERROR
from UI.ui_theme import apply_window_theme


class CasesListWindow(QWidget):
    """
    Cases list window:
    - lists all cases under default_cases_root()
    - opens a selected case
    - creates a new case (ZIP upload)
    - deletes a case folder
    """

    def __init__(self, state: Optional[AppState] = None):
        super().__init__()
        self.state = state or AppState()

        self.setWindowTitle("Mijn dossiers")
        self.setMinimumSize(1100, 720)
        self._center_on_screen()

        self.cases: List[Dict[str, Any]] = []

        self._build_ui()
        apply_window_theme(self)

        self.refresh_cases()

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(26, 22, 26, 26)
        wrapper.setSpacing(0)

        self.page = QFrame()
        self.page.setObjectName("page")

        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(60, 40, 60, 44)
        page_layout.setSpacing(12)

        title = QLabel("Mijn dossiers")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        page_layout.addWidget(title)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("fieldLabel")
        self.subtitle.setFont(QFont("Segoe UI", 12))
        page_layout.addWidget(self.subtitle)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Case ID",
            "Aangemaakt",
            "Bijgewerkt",
            "Documenten",
            "Done",
            "Errors",
            "Open",
            "Delete",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        page_layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.refresh_btn = QPushButton("Vernieuwen")
        self.refresh_btn.setObjectName("secondaryButton")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_cases)

        self.new_btn = QPushButton("Nieuw dossier (ZIP)")
        self.new_btn.setObjectName("primaryButton")
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.clicked.connect(self.open_zip_upload)

        btn_row.addWidget(self.refresh_btn, alignment=Qt.AlignLeft)
        btn_row.addStretch(1)
        btn_row.addWidget(self.new_btn, alignment=Qt.AlignRight)

        page_layout.addLayout(btn_row)

        wrapper.addWidget(self.page)
        container = QWidget()
        container.setLayout(wrapper)

        root.addWidget(container)
        self.setLayout(root)

    def refresh_cases(self) -> None:
        root = default_cases_root()
        root.mkdir(parents=True, exist_ok=True)

        self.cases = []

        for d in sorted(root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            mp = d / "manifest.json"
            if not mp.exists():
                continue

            try:
                st = AppState.load_manifest(mp)

                total_docs = len(st.documents)
                done = len([x for x in st.documents if x.status == DOC_STATUS_SUMMARIZED])
                err = len([x for x in st.documents if x.status == DOC_STATUS_ERROR])

                created = st.case.archive_created_at or ""
                updated = st.updated_at or ""

                self.cases.append({
                    "case_id": st.case.case_id or d.name,
                    "created": created,
                    "updated": updated,
                    "total_docs": total_docs,
                    "done": done,
                    "errors": err,
                    "manifest_path": mp,
                })
            except Exception:
                # Skip invalid manifests silently
                continue

        self._render_table()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self.cases))

        root = default_cases_root()
        self.subtitle.setText(f"Opslag: {root} • Dossiers: {len(self.cases)}")

        for row, item in enumerate(self.cases):
            self.table.setItem(row, 0, QTableWidgetItem(item["case_id"]))
            self.table.setItem(row, 1, QTableWidgetItem(item["created"]))
            self.table.setItem(row, 2, QTableWidgetItem(item["updated"]))
            self.table.setItem(row, 3, QTableWidgetItem(str(item["total_docs"])))
            self.table.setItem(row, 4, QTableWidgetItem(str(item["done"])))
            self.table.setItem(row, 5, QTableWidgetItem(str(item["errors"])))

            open_btn = QPushButton("Open")
            open_btn.setObjectName("secondaryButton")
            open_btn.clicked.connect(lambda _, r=row: self.open_case_by_row(r))

            del_btn = QPushButton("Delete")
            del_btn.setObjectName("secondaryButton")
            del_btn.clicked.connect(lambda _, r=row: self.delete_case_by_row(r))

            self.table.setCellWidget(row, 6, open_btn)
            self.table.setCellWidget(row, 7, del_btn)

    def open_case_by_row(self, row: int) -> None:
        if row < 0 or row >= len(self.cases):
            return

        mp: Path = self.cases[row]["manifest_path"]
        try:
            loaded = AppState.load_manifest(mp)

            # Keep current user/model context from current session
            loaded.user.email = self.state.user.email
            loaded.model = self.state.model

            from UI.dossier_documents_window import DossierDocumentsWindow

            self.close()
            self.next_window = DossierDocumentsWindow(state=loaded)
            self.next_window.show()

        except Exception as e:
            QMessageBox.critical(self, "Fout", f"Kan dossier niet openen:\n{e}")

    def delete_case_by_row(self, row: int) -> None:
        if row < 0 or row >= len(self.cases):
            return

        mp: Path = self.cases[row]["manifest_path"]
        case_dir = mp.parent

        reply = QMessageBox.question(
            self,
            "Bevestigen",
            f"Wil je dit dossier verwijderen?\n\n{case_dir}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            shutil.rmtree(case_dir)
            self.refresh_cases()
        except Exception as e:
            QMessageBox.critical(self, "Fout", f"Kan dossier niet verwijderen:\n{e}")

    def open_zip_upload(self) -> None:
        from UI.zip_upload_window import ZipUploadWindow

        self.close()
        self.zip_window = ZipUploadWindow(state=self.state)
        self.zip_window.show()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        rect = screen.availableGeometry()
        x = rect.x() + (rect.width() - self.width()) // 2
        y = rect.y() + (rect.height() - self.height()) // 2
        self.move(x, y)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = CasesListWindow()
    w.show()
    sys.exit(app.exec_())
