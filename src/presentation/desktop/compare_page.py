"""Compare page: candidate-minus-baseline deltas across archived runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src.presentation.desktop.formatting import PLACEHOLDER, format_number
from src.presentation.desktop.plots import ComparisonBarChart
from src.presentation.desktop.run_service import DesktopRunService
from src.presentation.desktop.theme import (
    COLORS,
    SPACE_LG,
    SPACE_MD,
    status_color,
)
from src.presentation.desktop.view_models import (
    STATISTICS_METRICS,
    build_comparison_view,
    build_history_rows,
    comparison_metric_series,
)
from src.presentation.desktop.widgets import (
    EmptyState,
    InlineBanner,
    SectionCard,
    configure_table,
    fill_table,
    table_item,
)


COMPARISON_HEADERS = (
    "Role",
    "Ammeter",
    "Status",
    "Archived",
    "Analyzed",
    "Mean",
    "Std dev",
    "Δ metric",
    "Comparable",
)

DELTA_COLUMN = COMPARISON_HEADERS.index("Δ metric")


class ComparePage(QWidget):
    """Pick one baseline plus candidates and inspect their deltas."""

    message = Signal(str, str)

    def __init__(
        self,
        service: DesktopRunService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._rows: List[Dict[str, Any]] = []
        self._comparison: Optional[Dict[str, Any]] = None
        self._view: Optional[Dict[str, Any]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_MD)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(2)
        title = QLabel("Compare runs")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Deltas are descriptive: candidate minus baseline, with no "
            "accuracy ranking implied."
        )
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button = QPushButton("Export comparison")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export)
        header.addWidget(self.refresh_button, 0)
        header.addWidget(self.export_button, 0)
        layout.addLayout(header)

        self.banner = InlineBanner()
        layout.addWidget(self.banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_selector())
        splitter.addWidget(self._build_results())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 900])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_selector(self) -> QWidget:
        card = SectionCard(
            "Selection",
            "One baseline, one or more candidates.",
        )
        card.setMinimumWidth(340)
        card.setMaximumWidth(460)

        card.content.addWidget(QLabel("Baseline"))
        self.baseline_combo = QComboBox()
        self.baseline_combo.currentIndexChanged.connect(
            self._baseline_changed
        )
        card.content.addWidget(self.baseline_combo)

        candidates_row = QHBoxLayout()
        candidates_row.addWidget(QLabel("Candidates"))
        candidates_row.addStretch(1)
        clear_button = QPushButton("Clear")
        clear_button.setObjectName("linkButton")
        clear_button.clicked.connect(self._clear_candidates)
        candidates_row.addWidget(clear_button)
        card.content.addLayout(candidates_row)

        self.candidate_list = QListWidget()
        self.candidate_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        self.candidate_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.candidate_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.candidate_list.itemChanged.connect(self._selection_changed)
        card.content.addWidget(self.candidate_list, 1)

        self.selection_hint = QLabel("Select a baseline and candidates.")
        self.selection_hint.setProperty("muted", "true")
        self.selection_hint.setWordWrap(True)
        card.content.addWidget(self.selection_hint)

        self.compare_button = QPushButton("Compare")
        self.compare_button.setObjectName("primaryButton")
        self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self.compare)
        card.content.addWidget(self.compare_button)
        return card

    def _build_results(self) -> QWidget:
        self.results_stack = QStackedWidget()
        self.results_empty = EmptyState(
            "No comparison yet",
            "Choose a baseline and at least one candidate, then press "
            "Compare.",
            framed=True,
        )

        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACE_MD)

        chart_card = SectionCard("Metric comparison")
        self.metric_combo = QComboBox()
        for metric in STATISTICS_METRICS:
            self.metric_combo.addItem(metric["label"], metric["key"])
        self.metric_combo.currentIndexChanged.connect(self._metric_changed)
        chart_card.add_header_widget(self.metric_combo)
        self.chart = ComparisonBarChart()
        self.chart.setMinimumHeight(240)
        chart_card.content.addWidget(self.chart, 1)
        column.addWidget(chart_card, 2)

        table_card = SectionCard(
            "Run statistics",
            "The baseline row is listed first.",
        )
        self.table = QTableWidget(0, len(COMPARISON_HEADERS))
        configure_table(
            self.table,
            COMPARISON_HEADERS,
            stretch_column=len(COMPARISON_HEADERS) - 1,
        )
        self.table.setSortingEnabled(False)
        table_card.content.addWidget(self.table, 1)
        column.addWidget(table_card, 3)

        self.results_stack.addWidget(self.results_empty)
        self.results_stack.addWidget(container)
        return self.results_stack

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Reload the archive into the baseline and candidate selectors."""
        try:
            runs = self._service.find_runs(limit=500)
        except Exception as exc:
            self.banner.show_message(
                f"Unable to read the archive — {exc}",
                "error",
            )
            runs = []
        else:
            self.banner.clear()
        self._rows = build_history_rows(runs)

        previous_baseline = self.baseline_combo.currentData()
        previous_candidates = set(self.selected_candidates())

        self.baseline_combo.blockSignals(True)
        self.candidate_list.blockSignals(True)
        self.baseline_combo.clear()
        self.candidate_list.clear()
        for row in self._rows:
            label = self._row_label(row)
            self.baseline_combo.addItem(label, row["run_id"])
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, row["run_id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if row["run_id"] in previous_candidates
                else Qt.CheckState.Unchecked
            )
            self.candidate_list.addItem(item)
        if previous_baseline is not None:
            index = self.baseline_combo.findData(previous_baseline)
            if index >= 0:
                self.baseline_combo.setCurrentIndex(index)
        self.baseline_combo.blockSignals(False)
        self.candidate_list.blockSignals(False)

        self._baseline_changed()

    @staticmethod
    def _row_label(row: Dict[str, Any]) -> str:
        return (
            f"{row['ammeter_display']} · {row['archived_at']} · "
            f"{row['status_display']} · {row['short_id']}"
        )

    def _clear_candidates(self) -> None:
        self.candidate_list.blockSignals(True)
        for index in range(self.candidate_list.count()):
            self.candidate_list.item(index).setCheckState(
                Qt.CheckState.Unchecked
            )
        self.candidate_list.blockSignals(False)
        self._selection_changed()

    def _baseline_changed(self, *_args: object) -> None:
        baseline = self.baseline_combo.currentData()
        self.candidate_list.blockSignals(True)
        for index in range(self.candidate_list.count()):
            item = self.candidate_list.item(index)
            is_baseline = item.data(Qt.ItemDataRole.UserRole) == baseline
            item.setHidden(is_baseline)
            if is_baseline:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.candidate_list.blockSignals(False)
        self._selection_changed()

    def selected_candidates(self) -> List[str]:
        """Return the checked candidate run IDs in list order."""
        return [
            str(self.candidate_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.candidate_list.count())
            if self.candidate_list.item(index).checkState()
            == Qt.CheckState.Checked
        ]

    def _selection_changed(self, *_args: object) -> None:
        candidates = self.selected_candidates()
        baseline = self.baseline_combo.currentData()
        ready = bool(baseline) and bool(candidates)
        self.compare_button.setEnabled(ready)
        if not self._rows:
            self.selection_hint.setText(
                "No archived runs yet. Run a test with archiving enabled."
            )
        elif not ready:
            self.selection_hint.setText(
                "Select a baseline and at least one candidate."
            )
        else:
            self.selection_hint.setText(
                f"{len(candidates)} candidate(s) versus the baseline."
            )

    # ------------------------------------------------------------------
    # comparison
    # ------------------------------------------------------------------
    def compare(self) -> None:
        """Load the comparison and render its chart and table."""
        baseline = self.baseline_combo.currentData()
        candidates = self.selected_candidates()
        if not baseline or not candidates:
            return
        try:
            self._comparison = self._service.compare_runs(
                str(baseline),
                candidates,
            )
        except Exception as exc:
            self._comparison = None
            self._view = None
            self.export_button.setEnabled(False)
            self.results_stack.setCurrentWidget(self.results_empty)
            self.banner.show_message(f"Comparison failed — {exc}", "error")
            return

        self.banner.clear()
        self._view = build_comparison_view(self._comparison)
        self.export_button.setEnabled(True)
        self.results_stack.setCurrentIndex(1)
        self._metric_changed()
        self.message.emit(
            f"Compared {len(candidates)} run(s) against the baseline",
            "success",
        )

    def _metric_changed(self, *_args: object) -> None:
        if self._view is None:
            return
        metric_key = str(self.metric_combo.currentData())
        metric = next(
            (
                item
                for item in STATISTICS_METRICS
                if item["key"] == metric_key
            ),
            STATISTICS_METRICS[0],
        )
        series = comparison_metric_series(self._view, metric_key)
        self.chart.set_series(
            series,
            label=str(metric["label"]),
            unit=str(metric["unit"]),
        )
        delta_header = self.table.horizontalHeaderItem(DELTA_COLUMN)
        if delta_header is not None:
            delta_header.setText(f"Δ {metric['label']}")
        self._fill_table(series)

    def _fill_table(self, series: List[Dict[str, Any]]) -> None:
        if self._view is None:
            return
        deltas = {entry["run_id"]: entry for entry in series}
        rows = []
        for entry in self._view["runs"]:
            statistics = entry.get("statistics") or {}
            delta = deltas.get(entry["run_id"], {})
            comparable_parts = []
            if entry["is_baseline"]:
                comparable_parts.append("baseline")
            else:
                comparable_parts.append(
                    "same ammeter"
                    if entry.get("same_ammeter_type")
                    else "different ammeter"
                )
                comparable_parts.append(
                    "same window"
                    if entry.get("same_sampling_settings")
                    else "different window"
                )
            rows.append(
                [
                    table_item(
                        "Baseline" if entry["is_baseline"] else "Candidate",
                        tooltip=entry["run_id"],
                        color=(
                            COLORS["accent"]
                            if entry["is_baseline"]
                            else None
                        ),
                    ),
                    table_item(entry["ammeter_display"]),
                    table_item(
                        entry["status_display"],
                        color=status_color(entry["status"]),
                    ),
                    table_item(entry["archived_at"]),
                    table_item(
                        str(statistics.get("measurements_count", PLACEHOLDER)),
                        align_right=True,
                    ),
                    table_item(
                        format_number(statistics.get("mean_current"), digits=5),
                        align_right=True,
                        monospace=True,
                        tooltip=(
                            "median "
                            + format_number(
                                statistics.get("median_current"),
                                digits=5,
                            )
                            + " · min "
                            + format_number(
                                statistics.get("minimum_current"),
                                digits=5,
                            )
                            + " · max "
                            + format_number(
                                statistics.get("maximum_current"),
                                digits=5,
                            )
                        ),
                    ),
                    table_item(
                        format_number(
                            statistics.get("standard_deviation_current"),
                            digits=4,
                        ),
                        align_right=True,
                        monospace=True,
                    ),
                    table_item(
                        PLACEHOLDER
                        if entry["is_baseline"]
                        else delta.get("delta_display", PLACEHOLDER),
                        align_right=True,
                        monospace=True,
                        color=self._delta_color(delta.get("delta")),
                    ),
                    table_item(", ".join(comparable_parts)),
                ]
            )
        fill_table(self.table, rows)

    @staticmethod
    def _delta_color(delta: object) -> Optional[str]:
        if not isinstance(delta, (int, float)) or isinstance(delta, bool):
            return None
        if delta > 0:
            return COLORS["blue"]
        if delta < 0:
            return COLORS["warning"]
        return None

    def _export(self) -> None:
        if self._comparison is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export comparison",
            "comparison.json",
            "JSON files (*.json)",
        )
        if not target:
            return
        try:
            Path(target).write_text(
                json.dumps(self._comparison, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            self.banner.show_message(f"Export failed — {exc}", "error")
            return
        self.message.emit(f"Exported {Path(target).name}", "success")
