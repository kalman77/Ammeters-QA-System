"""Results page: browse, inspect, and export archived test runs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.presentation.desktop.formatting import (
    PLACEHOLDER,
    format_number,
    format_percentage,
    title_case,
)
from src.presentation.desktop.plots import MeasurementPlot
from src.presentation.desktop.run_service import DesktopRunService
from src.presentation.desktop.theme import (
    COLORS,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    status_color,
)
from src.presentation.desktop.view_models import (
    STATISTICS_METRICS,
    build_error_lines,
    count_retried_samples,
    describe_retry_policy,
    build_history_rows,
    build_sample_rows,
    build_summary_cards,
    row_matches_search,
)
from src.presentation.desktop.widgets import (
    EmptyState,
    InlineBanner,
    MetricCard,
    SectionCard,
    StatusPill,
    configure_table,
    field_label,
    fill_table,
    table_item,
)


HISTORY_HEADERS = (
    "Archived",
    "Ammeter",
    "Status",
    "Samples",
    "Mean (A)",
    "Metadata",
)

SAMPLE_HEADERS = (
    "#",
    "Scheduled",
    "Started",
    "Timing error",
    "Latency",
    "Attempts",
    "Current",
    "Status",
    "Errors",
)


class ResultsPage(QWidget):
    """Filterable archive browser with a rich per-run detail pane."""

    message = Signal(str, str)

    def __init__(
        self,
        service: DesktopRunService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._runs: List[Dict[str, Any]] = []
        self._rows: List[Dict[str, Any]] = []
        self._visible_rows: List[Dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_MD)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(2)
        title = QLabel("Archived results")
        title.setObjectName("pageTitle")
        self.subtitle = QLabel("No archived runs loaded yet.")
        self.subtitle.setObjectName("pageSubtitle")
        heading.addWidget(title)
        heading.addWidget(self.subtitle)
        header.addLayout(heading, 1)

        self.open_folder_button = QPushButton("Open archive folder")
        self.open_folder_button.clicked.connect(self._open_archive_folder)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Reload the archive (F5)")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.open_folder_button, 0)
        header.addWidget(self.refresh_button, 0)
        layout.addLayout(header)

        self.banner = InlineBanner()
        layout.addWidget(self.banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_history_side())
        splitter.addWidget(self._build_detail_side())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([560, 720])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_history_side(self) -> QWidget:
        card = SectionCard("History", "Newest archived runs first.")

        filters = QHBoxLayout()
        filters.setSpacing(SPACE_SM)

        self.ammeter_filter = QComboBox()
        self.ammeter_filter.addItem("All ammeters", None)
        for name in self._service.ammeter_types:
            self.ammeter_filter.addItem(title_case(name), name)
        self.ammeter_filter.currentIndexChanged.connect(self.refresh)

        self.status_filter = QComboBox()
        self.status_filter.addItem("Any status", None)
        for value in ("success", "partial", "failed"):
            self.status_filter.addItem(title_case(value), value)
        self.status_filter.currentIndexChanged.connect(self.refresh)

        self.statistics_filter = QComboBox()
        self.statistics_filter.addItem("With or without stats", None)
        self.statistics_filter.addItem("Has statistics", True)
        self.statistics_filter.addItem("No statistics", False)
        self.statistics_filter.currentIndexChanged.connect(self.refresh)

        self.limit_input = QSpinBox()
        self.limit_input.setRange(1, 5000)
        self.limit_input.setValue(200)
        self.limit_input.setPrefix("limit ")
        self.limit_input.editingFinished.connect(self.refresh)

        for widget in (
            self.ammeter_filter,
            self.status_filter,
            self.statistics_filter,
            self.limit_input,
        ):
            filters.addWidget(widget)
        filters.addStretch(1)
        card.content.addLayout(filters)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Filter by run ID, ammeter, timestamp, or metadata (Ctrl+F)"
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_search)
        card.content.addWidget(self.search_input)

        self.history_stack = QStackedWidget()
        self.history_table = QTableWidget(0, len(HISTORY_HEADERS))
        configure_table(
            self.history_table,
            HISTORY_HEADERS,
            stretch_column=len(HISTORY_HEADERS) - 1,
        )
        self.history_table.itemSelectionChanged.connect(self._show_selection)
        self.history_empty = EmptyState(
            "No archived runs",
            "Start a run with archiving enabled, then refresh this page.",
        )
        self.history_stack.addWidget(self.history_table)
        self.history_stack.addWidget(self.history_empty)
        card.content.addWidget(self.history_stack, 1)
        return card

    def _build_detail_side(self) -> QWidget:
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACE_MD)

        self.detail_stack = QStackedWidget()
        self.detail_empty = EmptyState(
            "Select a run",
            "Pick an archived run on the left to inspect its samples, "
            "statistics, and raw archive document.",
            framed=True,
        )

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(SPACE_MD)

        header_card = SectionCard("Run detail")
        header_row = QHBoxLayout()
        header_row.setSpacing(SPACE_SM)
        self.detail_title = QLabel(PLACEHOLDER)
        self.detail_title.setObjectName("sectionTitle")
        self.detail_status = StatusPill()
        header_row.addWidget(self.detail_title, 0)
        header_row.addWidget(self.detail_status, 0)
        header_row.addStretch(1)
        header_card.content.addLayout(header_row)

        self.detail_run_id = QLabel(PLACEHOLDER)
        self.detail_run_id.setProperty("muted", "true")
        self.detail_run_id.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        header_card.content.addWidget(self.detail_run_id)

        actions = QHBoxLayout()
        actions.setSpacing(SPACE_SM)
        for label, slot, tooltip in (
            ("Copy run ID", self._copy_run_id, "Copy the canonical UUID"),
            ("Export JSON", self._export_json, "Save the archive document"),
            ("Export samples CSV", self._export_csv, "Save every slot"),
        ):
            button = QPushButton(label)
            button.setToolTip(tooltip)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        header_card.content.addLayout(actions)
        detail_layout.addWidget(header_card)

        cards_grid = QGridLayout()
        cards_grid.setSpacing(SPACE_SM)
        self.summary_cards: Dict[str, MetricCard] = {}
        for position, (key, label) in enumerate(
            (
                ("status", "STATUS"),
                ("samples", "ANALYZED SAMPLES"),
                ("mean", "MEAN CURRENT"),
                ("deviation", "STD DEVIATION"),
                ("retries", "RETRIED SLOTS"),
                ("window", "SAMPLING WINDOW"),
            )
        ):
            card = MetricCard(label, PLACEHOLDER, metric_key=key)
            self.summary_cards[key] = card
            grid_row, grid_column = divmod(position, 3)
            cards_grid.addWidget(card, grid_row, grid_column)
        for grid_column in range(3):
            cards_grid.setColumnStretch(grid_column, 1)
        detail_layout.addLayout(cards_grid)

        self.tabs = QTabWidget()
        self.plot = MeasurementPlot()
        self.tabs.addTab(self._wrap(self.plot), "Chart")

        self.samples_table = QTableWidget(0, len(SAMPLE_HEADERS))
        configure_table(
            self.samples_table,
            SAMPLE_HEADERS,
            stretch_column=len(SAMPLE_HEADERS) - 1,
        )
        self.tabs.addTab(self._wrap(self.samples_table), "Samples")

        self.statistics_table = QTableWidget(0, 2)
        configure_table(
            self.statistics_table,
            ("Metric", "Value"),
            stretch_column=1,
        )
        self.statistics_table.setSortingEnabled(False)
        statistics_panel = QWidget()
        statistics_layout = QVBoxLayout(statistics_panel)
        statistics_layout.setContentsMargins(
            SPACE_SM,
            SPACE_SM,
            SPACE_SM,
            SPACE_SM,
        )
        statistics_layout.setSpacing(SPACE_SM)
        statistics_layout.addWidget(self.statistics_table, 1)
        statistics_layout.addWidget(field_label("ERRORS"))
        self.error_view = QPlainTextEdit()
        self.error_view.setReadOnly(True)
        self.error_view.setMaximumHeight(140)
        statistics_layout.addWidget(self.error_view)
        self.tabs.addTab(statistics_panel, "Statistics")

        self.json_view = QPlainTextEdit()
        self.json_view.setReadOnly(True)
        self.json_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.tabs.addTab(self._wrap(self.json_view), "Archive JSON")

        detail_layout.addWidget(self.tabs, 1)

        self.detail_stack.addWidget(self.detail_empty)
        self.detail_stack.addWidget(detail)
        column.addWidget(self.detail_stack, 1)
        return container

    @staticmethod
    def _wrap(widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
        layout.addWidget(widget)
        return container

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Reload archived runs using the current filters."""
        try:
            self._runs = self._service.find_runs(
                ammeter_type=self.ammeter_filter.currentData(),
                status=self.status_filter.currentData(),
                has_statistics=self.statistics_filter.currentData(),
                limit=self.limit_input.value(),
            )
        except Exception as exc:
            self._runs = []
            self.banner.show_message(
                f"Unable to read the archive — {exc}",
                "error",
            )
        else:
            self.banner.clear()
        self._rows = build_history_rows(self._runs)
        self._apply_search()

    def _apply_search(self) -> None:
        needle = self.search_input.text()
        self._visible_rows = [
            row for row in self._rows if row_matches_search(row, needle)
        ]
        self._fill_history()
        total = len(self._rows)
        shown = len(self._visible_rows)
        if total == 0:
            self.subtitle.setText("No archived runs match the filters.")
        elif shown == total:
            self.subtitle.setText(f"{total} archived runs.")
        else:
            self.subtitle.setText(f"{shown} of {total} archived runs shown.")

    def _fill_history(self) -> None:
        rows = []
        for row in self._visible_rows:
            rows.append(
                [
                    table_item(
                        row["archived_at"],
                        sort_value=row["archived_at_raw"],
                        tooltip=row["run_id"],
                    ),
                    table_item(row["ammeter_display"]),
                    table_item(
                        row["status_display"],
                        color=status_color(row["status"]),
                    ),
                    table_item(
                        row["samples_display"],
                        sort_value=row.get("analyzed_samples") or 0,
                        align_right=True,
                        tooltip=(
                            f"{format_percentage(row['success_ratio'])} usable"
                            f" · {row['frequency_display']}"
                        ),
                    ),
                    table_item(
                        row["mean_display"],
                        sort_value=row["mean_current"],
                        align_right=True,
                        monospace=True,
                        tooltip=f"std dev {row['deviation_display']}",
                    ),
                    table_item(
                        row["metadata_display"],
                        tooltip=row["metadata_display"],
                    ),
                ]
            )
        fill_table(self.history_table, rows)
        # The archive already returns newest-first; keep the indicator honest.
        self.history_table.horizontalHeader().setSortIndicator(
            0,
            Qt.SortOrder.DescendingOrder,
        )
        self.history_stack.setCurrentWidget(
            self.history_table if rows else self.history_empty
        )
        if not rows:
            self._clear_detail()

    def _selected_row(self) -> Optional[Dict[str, Any]]:
        selection = self.history_table.selectionModel()
        if selection is None:
            return None
        indexes = selection.selectedRows()
        if not indexes:
            return None
        position = indexes[0].row()
        item = self.history_table.item(position, 0)
        if item is None:
            return None
        run_id = item.toolTip()
        return next(
            (row for row in self._visible_rows if row["run_id"] == run_id),
            None,
        )

    def selected_run(self) -> Optional[Dict[str, Any]]:
        """Return the full archived-run document for the selection."""
        row = self._selected_row()
        if row is None:
            return None
        return next(
            (
                run
                for run in self._runs
                if str(run.get("run_id")) == row["run_id"]
            ),
            None,
        )

    def _show_selection(self) -> None:
        run = self.selected_run()
        if run is None:
            self._clear_detail()
            return
        analysis = run.get("analysis") or {}

        self.detail_stack.setCurrentIndex(1)
        self.detail_title.setText(
            title_case(analysis.get("ammeter_type")) + " run"
        )
        self.detail_status.set_status(
            title_case(analysis.get("status")),
            str(analysis.get("status", "")),
        )
        self.detail_run_id.setText(
            f"{run.get('run_id')}  ·  archived "
            f"{self._archived_display(run)}"
        )

        for card in build_summary_cards(analysis):
            widget = self.summary_cards.get(card["key"])
            if widget is not None:
                widget.update_card(card["value"], card["hint"])

        self.plot.show_analysis(analysis)
        self._fill_samples(analysis)
        self._fill_statistics(run, analysis)
        self.json_view.setPlainText(json.dumps(run, indent=2, sort_keys=True))

    def _archived_display(self, run: Mapping[str, Any]) -> str:
        row = next(
            (
                item
                for item in self._rows
                if item["run_id"] == str(run.get("run_id"))
            ),
            None,
        )
        return row["archived_at"] if row else PLACEHOLDER

    def _fill_samples(self, analysis: Mapping[str, Any]) -> None:
        rows = []
        for sample in build_sample_rows(analysis):
            rows.append(
                [
                    table_item(
                        str(sample["index"]),
                        sort_value=sample["index"],
                        align_right=True,
                    ),
                    table_item(sample["scheduled_display"], align_right=True),
                    table_item(sample["started_display"], align_right=True),
                    table_item(
                        sample["timing_error_display"],
                        align_right=True,
                        monospace=True,
                    ),
                    table_item(
                        sample["latency_display"],
                        align_right=True,
                        monospace=True,
                    ),
                    table_item(
                        sample["attempts_display"],
                        sort_value=sample["attempts"],
                        align_right=True,
                        color=(
                            COLORS["warning"]
                            if (sample["attempts"] or 0) > 1
                            else None
                        ),
                    ),
                    table_item(
                        sample["current_display"],
                        align_right=True,
                        monospace=True,
                    ),
                    table_item(
                        sample["status_display"],
                        color=status_color(sample["status"]),
                    ),
                    table_item(
                        sample["error_display"],
                        tooltip=sample["error_display"],
                    ),
                ]
            )
        fill_table(self.samples_table, rows)

    def _fill_statistics(
        self,
        run: Mapping[str, Any],
        analysis: Mapping[str, Any],
    ) -> None:
        statistics = analysis.get("statistics") or {}
        summary = analysis.get("summary") or {}
        settings = (analysis.get("sampling_result") or {}).get(
            "settings"
        ) or {}
        unit = str(analysis.get("unit", "A"))

        rows = []
        for metric in STATISTICS_METRICS:
            value = statistics.get(metric["key"])
            suffix = f" {unit}" if metric["unit"] else ""
            rows.append(
                [
                    table_item(metric["label"]),
                    table_item(
                        format_number(
                            value,
                            digits=max(1, int(metric["digits"]) or 1),
                            suffix=suffix,
                        ),
                        monospace=True,
                    ),
                ]
            )
        for label, value in (
            ("Planned samples", summary.get("planned_samples")),
            ("Recorded samples", summary.get("recorded_samples")),
            ("Excluded samples", summary.get("excluded_samples")),
            ("Failed samples", summary.get("failed_samples")),
            ("Missed slots", summary.get("missed_samples")),
            (
                "Configured frequency",
                format_number(
                    settings.get("sampling_frequency_hz"),
                    digits=5,
                    suffix=" Hz",
                ),
            ),
            (
                "Configured duration",
                format_number(
                    settings.get("total_duration_seconds"),
                    digits=5,
                    suffix=" s",
                ),
            ),
            ("Deviation method", "population"),
            ("Retry policy", describe_retry_policy(analysis)),
            ("Retried slots", count_retried_samples(analysis)),
            (
                "Metadata",
                ", ".join(
                    f"{key}={value}"
                    for key, value in sorted(
                        (run.get("metadata") or {}).items()
                    )
                )
                or PLACEHOLDER,
            ),
        ):
            rows.append(
                [
                    table_item(label),
                    table_item(
                        PLACEHOLDER if value is None else str(value),
                        monospace=True,
                    ),
                ]
            )
        fill_table(self.statistics_table, rows)

        errors = build_error_lines(analysis)
        self.error_view.setPlainText(
            "\n".join(errors) if errors else "No errors were recorded."
        )

    def _clear_detail(self) -> None:
        self.detail_stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def focus_search(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _copy_run_id(self) -> None:
        run = self.selected_run()
        if run is None:
            return
        QGuiApplication.clipboard().setText(str(run.get("run_id", "")))
        self.message.emit("Run ID copied to the clipboard", "info")

    def _open_archive_folder(self) -> None:
        try:
            directory = self._service.archive_directory
        except Exception as exc:
            self.banner.show_message(
                f"Archive directory is not configured — {exc}",
                "error",
            )
            return
        if not Path(directory).exists():
            self.banner.show_message(
                f"Archive directory does not exist yet: {directory}",
                "warning",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _export_json(self) -> None:
        run = self.selected_run()
        if run is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export archive document",
            f"{run.get('run_id', 'run')}.json",
            "JSON files (*.json)",
        )
        if not target:
            return
        try:
            Path(target).write_text(
                json.dumps(run, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            self.banner.show_message(f"Export failed — {exc}", "error")
            return
        self.message.emit(f"Exported {Path(target).name}", "success")

    def _export_csv(self) -> None:
        run = self.selected_run()
        if run is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export samples",
            f"{run.get('run_id', 'run')}-samples.csv",
            "CSV files (*.csv)",
        )
        if not target:
            return
        analysis = run.get("analysis") or {}
        samples = (analysis.get("sampling_result") or {}).get("samples") or []
        try:
            with open(target, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "sample_index",
                        "scheduled_elapsed_seconds",
                        "started_elapsed_seconds",
                        "timing_error_seconds",
                        "request_latency_seconds",
                        "current",
                        "unit",
                        "status",
                        "errors",
                    ]
                )
                for sample in samples:
                    result = sample.get("result") or {}
                    writer.writerow(
                        [
                            sample.get("sample_index"),
                            sample.get("scheduled_elapsed_seconds"),
                            sample.get("started_elapsed_seconds"),
                            sample.get("timing_error_seconds"),
                            result.get("request_latency_seconds"),
                            result.get("current"),
                            result.get("unit"),
                            result.get("status"),
                            "; ".join(
                                f"{error.get('code')}: {error.get('message')}"
                                for error in result.get("errors") or []
                            ),
                        ]
                    )
        except OSError as exc:
            self.banner.show_message(f"Export failed — {exc}", "error")
            return
        self.message.emit(
            f"Exported {len(samples)} samples to {Path(target).name}",
            "success",
        )
