"""Main window: sidebar navigation over the run, results, and compare pages."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.presentation.desktop.compare_page import ComparePage
from src.presentation.desktop.results_page import ResultsPage
from src.presentation.desktop.run_page import RunPage
from src.presentation.desktop.run_service import DesktopRunService
from src.presentation.desktop.theme import (
    COLORS,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
)


NAV_ITEMS = (
    ("Run", "Configure and execute a sampling window"),
    ("Results", "Browse and inspect archived runs"),
    ("Compare", "Diff archived runs against a baseline"),
)


class MainWindow(QMainWindow):
    """Compose the desktop pages and the shared navigation chrome."""

    def __init__(
        self,
        service: DesktopRunService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._settings = QSettings("AmmeterQA", "AmmeterDesktop")

        self.setWindowTitle("Ammeter QA · Test Console")
        self.setMinimumSize(1180, 720)

        root = QWidget()
        root.setObjectName("appRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.pages = QStackedWidget()
        self.run_page = RunPage(service, self._settings)
        self.results_page = ResultsPage(service)
        self.compare_page = ComparePage(service)
        for page in (self.run_page, self.results_page, self.compare_page):
            self.pages.addWidget(page)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        self.statusBar().showMessage(
            f"Config: {service.config_path}"
        )

        self.run_page.busy_changed.connect(self._on_busy_changed)
        self.run_page.run_completed.connect(self._on_run_completed)
        for page in (self.run_page, self.results_page, self.compare_page):
            page.message.connect(self._show_status_message)

        self._install_shortcuts()
        self._restore_geometry()
        QTimer.singleShot(0, self._initial_load)

    # ------------------------------------------------------------------
    # chrome
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(216)
        column = QVBoxLayout(sidebar)
        column.setContentsMargins(SPACE_MD, SPACE_LG, SPACE_MD, SPACE_MD)
        column.setSpacing(SPACE_SM)

        brand_mark = QLabel("AMMETER QA")
        brand_mark.setObjectName("brandMark")
        brand_title = QLabel("Test Console")
        brand_title.setObjectName("brandTitle")
        brand_caption = QLabel(
            f"{len(self._service.ammeter_types)} ammeters configured"
        )
        brand_caption.setObjectName("brandCaption")
        column.addWidget(brand_mark)
        column.addWidget(brand_title)
        column.addWidget(brand_caption)
        column.addSpacing(SPACE_LG)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: List[QPushButton] = []
        for index, (label, tooltip) in enumerate(NAV_ITEMS):
            button = QPushButton(f"{label}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setToolTip(f"{tooltip}  (Ctrl+{index + 1})")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, position=index: self.navigate(position)
            )
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            column.addWidget(button)

        column.addStretch(1)
        self.busy_label = QLabel("Idle")
        self.busy_label.setObjectName("sidebarFooter")
        column.addWidget(self.busy_label)
        hint = QLabel("Ctrl+R run · Esc stop · F5 refresh")
        hint.setObjectName("sidebarFooter")
        hint.setWordWrap(True)
        column.addWidget(hint)

        self.nav_buttons[0].setChecked(True)
        return sidebar

    def _install_shortcuts(self) -> None:
        for index in range(len(NAV_ITEMS)):
            QShortcut(
                QKeySequence(f"Ctrl+{index + 1}"),
                self,
                activated=lambda position=index: self.navigate(position),
            )
        QShortcut(
            QKeySequence("Ctrl+R"),
            self,
            activated=self._start_run_shortcut,
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Escape),
            self,
            activated=self.run_page.request_stop,
        )
        QShortcut(QKeySequence("F5"), self, activated=self._refresh_current)
        QShortcut(
            QKeySequence("Ctrl+F"),
            self,
            activated=self._focus_search,
        )

    # ------------------------------------------------------------------
    # behaviour
    # ------------------------------------------------------------------
    def navigate(self, index: int) -> None:
        """Switch to one page and keep the sidebar selection in sync."""
        if not 0 <= index < self.pages.count():
            return
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        if index in (1, 2):
            self._refresh_current()

    def _initial_load(self) -> None:
        self.results_page.refresh()
        self.compare_page.refresh()

    def _refresh_current(self) -> None:
        current = self.pages.currentWidget()
        if current is self.results_page:
            self.results_page.refresh()
        elif current is self.compare_page:
            self.compare_page.refresh()

    def _focus_search(self) -> None:
        if self.pages.currentWidget() is self.results_page:
            self.results_page.focus_search()

    def _start_run_shortcut(self) -> None:
        self.navigate(0)
        self.run_page.start_run()

    def _on_busy_changed(self, busy: bool) -> None:
        self.busy_label.setText("Running…" if busy else "Idle")
        self.busy_label.setStyleSheet(
            f"color:{COLORS['accent'] if busy else COLORS['muted']};"
        )

    def _on_run_completed(self, _outcome: dict) -> None:
        self.results_page.refresh()
        self.compare_page.refresh()

    def _show_status_message(self, message: str, level: str = "info") -> None:
        self.statusBar().showMessage(message, 6000)

    # ------------------------------------------------------------------
    # window state
    # ------------------------------------------------------------------
    def _restore_geometry(self) -> None:
        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Confirm before closing while a run is still executing."""
        if self.run_page.is_busy:
            answer = QMessageBox.question(
                self,
                "Stop the running test?",
                "A sampling run is still executing. Stop it and close the "
                "application?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.run_page.request_stop()
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.sync()
        super().closeEvent(event)
