"""Run page: configure a sampling window and watch it execute live."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src.presentation.desktop.formatting import (
    PLACEHOLDER,
    format_number,
    format_seconds,
    title_case,
)
from src.presentation.desktop.plots import MeasurementPlot
from src.domain.models.retry_policy import (
    MAX_ATTEMPTS_PER_SLOT,
    MAX_RETRY_DELAY_SECONDS,
)
from src.presentation.desktop.run_service import (
    DesktopRunService,
    FaultInjection,
    RunRequest,
    StopToken,
)
from src.presentation.desktop.theme import (
    COLORS,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    status_color,
)
from src.presentation.desktop.view_models import (
    build_summary_cards,
    count_retried_samples,
)
from src.presentation.desktop.widgets import (
    InlineBanner,
    MetricCard,
    SectionCard,
    configure_table,
    field_label,
    fill_table,
    table_item,
)
from src.presentation.desktop.workers import RunWorker


STAGE_LABELS = {
    "sampling": "Sampling",
    "archiving": "Archiving",
    "done": "Complete",
    "failed": "Failed",
    "cancelled": "Stopped",
    "queued": "Queued",
}

RUN_TABLE_HEADERS = (
    "Ammeter",
    "Stage",
    "Slots",
    "Failed requests",
    "Mean current",
    "Status",
)


class RunPage(QWidget):
    """Left-hand run controls beside a live sampling workspace."""

    busy_changed = Signal(bool)
    run_completed = Signal(dict)
    message = Signal(str, str)

    def __init__(
        self,
        service: DesktopRunService,
        settings: QSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._settings = settings
        self._thread: Optional[QThread] = None
        self._worker: Optional[RunWorker] = None
        self._stop_token: Optional[StopToken] = None
        self._expected_samples = 0
        self._received_samples = 0
        self._completed_slots = 0
        self._failed_samples = 0
        self._live_state: Dict[str, Dict[str, Any]] = {}
        self._analyses: Dict[str, Dict[str, Any]] = {}
        self._ammeter_checks: Dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_MD)

        heading = QVBoxLayout()
        heading.setSpacing(2)
        title = QLabel("Run sampling test")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Sample the configured ammeter emulators, analyze the readings, "
            "and archive the run."
        )
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        layout.addLayout(heading)

        self.banner = InlineBanner()
        layout.addWidget(self.banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_workspace())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([440, 900])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        self._restore_settings()
        self._update_derived_window()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_controls(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("runControlsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content.setObjectName("runControlsContent")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, SPACE_SM, 0)
        column.setSpacing(SPACE_MD)

        column.addWidget(self._build_ammeter_card())
        column.addWidget(self._build_window_card())
        column.addWidget(self._build_retry_card())
        column.addWidget(self._build_fault_card())
        column.addWidget(self._build_archive_card())

        actions = QHBoxLayout()
        actions.setSpacing(SPACE_SM)
        self.start_button = QPushButton("Start run")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setToolTip("Start the sampling run (Ctrl+R)")
        self.start_button.clicked.connect(self.start_run)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setToolTip(
            "Stop after the current request (Esc)"
        )
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.request_stop)
        actions.addWidget(self.start_button, 1)
        actions.addWidget(self.stop_button, 0)
        column.addLayout(actions)
        column.addStretch(1)

        scroll.setWidget(content)
        scroll.setMinimumWidth(430)
        scroll.setMaximumWidth(540)
        return scroll

    def _build_ammeter_card(self) -> SectionCard:
        card = SectionCard(
            "Ammeters",
            "Each selected ammeter runs its own sampling window.",
        )
        select_all = QPushButton("All")
        select_all.setObjectName("linkButton")
        select_all.clicked.connect(lambda: self._set_all_ammeters(True))
        clear_all = QPushButton("None")
        clear_all.setObjectName("linkButton")
        clear_all.clicked.connect(lambda: self._set_all_ammeters(False))
        card.add_header_widget(select_all)
        card.add_header_widget(clear_all)

        for name in self._service.ammeter_types:
            checkbox = QCheckBox(title_case(name))
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._update_derived_window)
            self._ammeter_checks[name] = checkbox
            card.content.addWidget(checkbox)

        if not self._ammeter_checks:
            empty = QLabel("No ammeters are configured in config.yaml.")
            empty.setProperty("muted", "true")
            empty.setWordWrap(True)
            card.content.addWidget(empty)
        return card

    def _build_window_card(self) -> SectionCard:
        defaults = self._service.default_sampling()
        card = SectionCard(
            "Sampling window",
            "Duration is derived from N = D × F.",
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_MD)
        grid.setVerticalSpacing(SPACE_SM)

        self.count_input = QSpinBox()
        self.count_input.setRange(1, 100_000)
        self.count_input.setValue(
            int(defaults.get("measurements_count") or 20)
        )
        self.count_input.valueChanged.connect(self._update_derived_window)

        self.frequency_input = QDoubleSpinBox()
        self.frequency_input.setDecimals(3)
        self.frequency_input.setRange(0.001, 10_000.0)
        self.frequency_input.setSingleStep(0.5)
        self.frequency_input.setSuffix(" Hz")
        self.frequency_input.setValue(
            float(defaults.get("sampling_frequency_hz") or 5.0)
        )
        self.frequency_input.valueChanged.connect(self._update_derived_window)

        grid.addWidget(field_label("MEASUREMENTS (N)"), 0, 0)
        grid.addWidget(field_label("FREQUENCY (F)"), 0, 1)
        grid.addWidget(self.count_input, 1, 0)
        grid.addWidget(self.frequency_input, 1, 1)
        card.content.addLayout(grid)

        self.window_summary = QLabel()
        self.window_summary.setProperty("muted", "true")
        self.window_summary.setWordWrap(True)
        card.content.addWidget(self.window_summary)

        presets = QHBoxLayout()
        presets.setSpacing(SPACE_SM)
        for label, count, frequency in (
            ("Quick", 10, 5.0),
            ("Standard", 50, 10.0),
            ("Extended", 300, 20.0),
        ):
            button = QPushButton(label)
            button.setToolTip(f"{count} measurements at {frequency:g} Hz")
            button.clicked.connect(
                lambda _checked=False, c=count, f=frequency: (
                    self._apply_preset(c, f)
                )
            )
            presets.addWidget(button)
        card.content.addLayout(presets)
        return card

    def _build_retry_card(self) -> SectionCard:
        defaults = self._service.retry_defaults()
        card = SectionCard(
            "Retries",
            "Retries stay inside their own slot, so the schedule never slips.",
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_MD)
        grid.setVerticalSpacing(SPACE_SM)

        self.attempts_input = QSpinBox()
        self.attempts_input.setRange(1, MAX_ATTEMPTS_PER_SLOT)
        self.attempts_input.setValue(
            int(defaults.get("max_attempts") or 1)
        )
        self.attempts_input.setToolTip(
            "Requests permitted per slot, including the first"
        )
        self.attempts_input.valueChanged.connect(self._update_retry_inputs)

        self.retry_delay_input = QDoubleSpinBox()
        self.retry_delay_input.setDecimals(3)
        self.retry_delay_input.setRange(0.0, MAX_RETRY_DELAY_SECONDS)
        self.retry_delay_input.setSingleStep(0.01)
        self.retry_delay_input.setSuffix(" s")
        self.retry_delay_input.setValue(
            float(defaults.get("retry_delay_seconds") or 0.0)
        )

        grid.addWidget(field_label("ATTEMPTS PER SLOT"), 0, 0)
        grid.addWidget(field_label("BACKOFF"), 0, 1)
        grid.addWidget(self.attempts_input, 1, 0)
        grid.addWidget(self.retry_delay_input, 1, 1)
        card.content.addLayout(grid)

        self.retry_summary = QLabel()
        self.retry_summary.setProperty("muted", "true")
        self.retry_summary.setWordWrap(True)
        card.content.addWidget(self.retry_summary)
        self._update_retry_inputs()
        return card

    def _build_fault_card(self) -> SectionCard:
        card = SectionCard(
            "Fault injection",
            "Applied at the client boundary; the framework stays untouched.",
        )
        self.faults_enabled = QCheckBox("Enable injected faults")
        self.faults_enabled.toggled.connect(self._update_fault_inputs)
        card.content.addWidget(self.faults_enabled)

        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_MD)
        grid.setVerticalSpacing(SPACE_SM)
        self.fault_inputs: Dict[str, QDoubleSpinBox] = {}
        specs = (
            ("communication_failure_probability", "COMM FAILURE", 1.0),
            ("invalid_data_probability", "INVALID DATA", 1.0),
            ("outlier_probability", "OUTLIER", 1.0),
            ("extra_latency_probability", "EXTRA LATENCY", 1.0),
        )
        for index, (key, label, maximum) in enumerate(specs):
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setRange(0.0, maximum)
            spin.setSingleStep(0.05)
            self.fault_inputs[key] = spin
            row, column = divmod(index, 2)
            grid.addWidget(field_label(label), row * 2, column)
            grid.addWidget(spin, row * 2 + 1, column)

        self.outlier_offset = QDoubleSpinBox()
        self.outlier_offset.setDecimals(3)
        self.outlier_offset.setRange(0.0, 1000.0)
        self.outlier_offset.setValue(0.5)
        self.outlier_offset.setSuffix(" A")
        self.latency_penalty = QDoubleSpinBox()
        self.latency_penalty.setDecimals(3)
        self.latency_penalty.setRange(0.0, 5.0)
        self.latency_penalty.setValue(0.03)
        self.latency_penalty.setSuffix(" s")
        grid.addWidget(field_label("OUTLIER OFFSET"), 4, 0)
        grid.addWidget(field_label("LATENCY PENALTY"), 4, 1)
        grid.addWidget(self.outlier_offset, 5, 0)
        grid.addWidget(self.latency_penalty, 5, 1)

        self.random_seed = QSpinBox()
        self.random_seed.setRange(0, 2_147_483_647)
        self.random_seed.setValue(1979)
        grid.addWidget(field_label("RANDOM SEED"), 6, 0)
        grid.addWidget(self.random_seed, 7, 0)

        card.content.addLayout(grid)
        self._fault_widgets = [
            *self.fault_inputs.values(),
            self.outlier_offset,
            self.latency_penalty,
            self.random_seed,
        ]
        self._update_fault_inputs(False)
        return card

    def _build_archive_card(self) -> SectionCard:
        card = SectionCard(
            "Archive",
            "Archived runs appear on the Results and Compare pages.",
        )
        self.archive_toggle = QCheckBox("Archive each completed analysis")
        self.archive_toggle.setChecked(True)
        self.archive_toggle.toggled.connect(self._update_metadata_inputs)
        card.content.addWidget(self.archive_toggle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_MD)
        grid.setVerticalSpacing(SPACE_SM)
        self.metadata_label = QLineEdit()
        self.metadata_label.setPlaceholderText("e.g. bench-a")
        self.metadata_operator = QLineEdit()
        self.metadata_operator.setPlaceholderText("e.g. nir")
        self.metadata_note = QLineEdit()
        self.metadata_note.setPlaceholderText("optional note")
        grid.addWidget(field_label("LABEL"), 0, 0)
        grid.addWidget(field_label("OPERATOR"), 0, 1)
        grid.addWidget(self.metadata_label, 1, 0)
        grid.addWidget(self.metadata_operator, 1, 1)
        grid.addWidget(field_label("NOTE"), 2, 0, 1, 2)
        grid.addWidget(self.metadata_note, 3, 0, 1, 2)
        card.content.addLayout(grid)
        return card

    def _build_workspace(self) -> QWidget:
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACE_MD)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(SPACE_SM)
        self.cards = {
            "progress": MetricCard("PROGRESS", "Idle", metric_key="progress"),
            "samples": MetricCard("SLOTS", "0", metric_key="samples"),
            "failures": MetricCard(
                "FAILED REQUESTS",
                "0",
                metric_key="failures",
            ),
            "mean": MetricCard(
                "LATEST MEAN",
                PLACEHOLDER,
                metric_key="mean",
            ),
            "retried": MetricCard("RETRIED", "0", metric_key="retried"),
            "archived": MetricCard("ARCHIVED", "0", metric_key="archived"),
        }
        for card in self.cards.values():
            cards_row.addWidget(card, 1)
        column.addLayout(cards_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        column.addWidget(self.progress)

        plot_card = SectionCard(
            "Live measurements",
            "Successful readings, failures, and per-request latency.",
        )
        self.plot = MeasurementPlot()
        plot_card.content.addWidget(self.plot, 1)
        column.addWidget(plot_card, 3)

        table_card = SectionCard("Per-ammeter progress")
        self.run_table = QTableWidget(0, len(RUN_TABLE_HEADERS))
        configure_table(self.run_table, RUN_TABLE_HEADERS, stretch_column=0)
        self.run_table.setSortingEnabled(False)
        self.run_table.setMinimumHeight(140)
        table_card.content.addWidget(self.run_table)
        column.addWidget(table_card, 1)
        return container

    # ------------------------------------------------------------------
    # control helpers
    # ------------------------------------------------------------------
    def _set_all_ammeters(self, checked: bool) -> None:
        for checkbox in self._ammeter_checks.values():
            checkbox.setChecked(checked)

    def _apply_preset(self, count: int, frequency: float) -> None:
        self.count_input.setValue(count)
        self.frequency_input.setValue(frequency)

    def _update_retry_inputs(self, *_args: object) -> None:
        attempts = self.attempts_input.value()
        self.retry_delay_input.setEnabled(attempts > 1)
        if attempts <= 1:
            self.retry_summary.setText(
                "One request per slot; a failed slot is recorded as failed."
            )
            return
        slot_period = (
            1.0 / self.frequency_input.value()
            if self.frequency_input.value() > 0
            else 0.0
        )
        self.retry_summary.setText(
            f"Up to {attempts} requests per slot within its "
            f"{format_seconds(slot_period)} window. A slot that recovers is "
            "recorded as successful with its attempt count."
        )

    def _update_fault_inputs(self, enabled: bool) -> None:
        for widget in getattr(self, "_fault_widgets", []):
            widget.setEnabled(bool(enabled))

    def _update_metadata_inputs(self, enabled: bool) -> None:
        for widget in (
            self.metadata_label,
            self.metadata_operator,
            self.metadata_note,
        ):
            widget.setEnabled(bool(enabled))

    def _update_derived_window(self, *_args: object) -> None:
        count = self.count_input.value()
        frequency = self.frequency_input.value()
        duration = count / frequency if frequency > 0 else 0.0
        selected = len(self._selected_ammeters())
        self.window_summary.setText(
            f"Window {format_seconds(duration)} per ammeter · "
            f"{selected} selected · "
            f"{count * selected} measurements total"
        )
        if hasattr(self, "retry_summary"):
            self._update_retry_inputs()

    def _selected_ammeters(self) -> Tuple[str, ...]:
        return tuple(
            name
            for name, checkbox in self._ammeter_checks.items()
            if checkbox.isChecked()
        )

    def _collect_metadata(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        for key, widget in (
            ("label", self.metadata_label),
            ("operator", self.metadata_operator),
            ("note", self.metadata_note),
        ):
            text = widget.text().strip()
            if text:
                metadata[key] = text
        if self.faults_enabled.isChecked():
            metadata["faults_injected"] = True
        if self.attempts_input.value() > 1:
            metadata["max_attempts"] = self.attempts_input.value()
        return metadata

    def _collect_request(self) -> RunRequest:
        faults = FaultInjection(
            enabled=self.faults_enabled.isChecked(),
            communication_failure_probability=self.fault_inputs[
                "communication_failure_probability"
            ].value(),
            invalid_data_probability=self.fault_inputs[
                "invalid_data_probability"
            ].value(),
            outlier_probability=self.fault_inputs[
                "outlier_probability"
            ].value(),
            outlier_offset_amperes=self.outlier_offset.value(),
            extra_latency_probability=self.fault_inputs[
                "extra_latency_probability"
            ].value(),
            extra_latency_seconds=self.latency_penalty.value(),
            random_seed=self.random_seed.value(),
        )
        attempts = self.attempts_input.value()
        return RunRequest(
            ammeter_types=self._selected_ammeters(),
            measurements_count=self.count_input.value(),
            sampling_frequency_hz=self.frequency_input.value(),
            archive_results=self.archive_toggle.isChecked(),
            max_attempts=attempts,
            retry_delay_seconds=(
                self.retry_delay_input.value() if attempts > 1 else 0.0
            ),
            metadata=self._collect_metadata(),
            faults=faults,
        )

    # ------------------------------------------------------------------
    # run lifecycle
    # ------------------------------------------------------------------
    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def start_run(self) -> None:
        """Validate the controls and start one background run."""
        if self.is_busy:
            return
        try:
            request = self._collect_request()
        except ValueError as exc:
            self.banner.show_message(str(exc), "error")
            return

        self.banner.clear()
        self._expected_samples = request.total_samples
        self._received_samples = 0
        self._completed_slots = 0
        self._failed_samples = 0
        self._live_state = {
            name: {
                "stage": "queued",
                "slots": 0,
                "requests": 0,
                "failures": 0,
                "mean": None,
                "status": "",
            }
            for name in request.ammeter_types
        }
        self._analyses = {}
        self.plot.reset()
        self.progress.setValue(0)
        self.cards["progress"].update_card("Starting…", "", emphasis=True)
        self.cards["samples"].update_card("0", "0 requests")
        self.cards["failures"].update_card("0")
        self.cards["mean"].update_card(PLACEHOLDER, "")
        self.cards["retried"].update_card("0")
        self.cards["archived"].update_card("0")
        self._refresh_run_table()
        self._save_settings()

        self._stop_token = StopToken()
        self._worker = RunWorker(self._service, request, self._stop_token)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.samples_ready.connect(self._on_samples)
        self._worker.stage_changed.connect(self._on_stage)
        self._worker.analysis_ready.connect(self._on_analysis)
        self._worker.finished_ok.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)

        self._set_busy(True)
        self._thread.start()

    def request_stop(self) -> None:
        """Ask the running worker to stop at its next safe point."""
        if self._stop_token is None:
            return
        self._stop_token.request()
        self.stop_button.setEnabled(False)
        self.cards["progress"].update_card("Stopping…")

    def _set_busy(self, busy: bool) -> None:
        self.start_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        for widget in (
            self.count_input,
            self.frequency_input,
            self.archive_toggle,
            self.faults_enabled,
        ):
            widget.setEnabled(not busy)
        for checkbox in self._ammeter_checks.values():
            checkbox.setEnabled(not busy)
        self.busy_changed.emit(busy)

    def _on_samples(
        self,
        batch: Sequence[Tuple[str, Mapping[str, Any]]],
    ) -> None:
        self.plot.extend_live(batch)
        for ammeter_type, sample in batch:
            state = self._live_state.setdefault(
                ammeter_type,
                {
                    "stage": "sampling",
                    "slots": 0,
                    "requests": 0,
                    "failures": 0,
                    "mean": None,
                    "status": "",
                },
            )
            state["requests"] += 1
            self._received_samples += 1
            # Retries repeat a slot index, so progress tracks slots reached
            # rather than requests issued.
            slot_index = sample.get("sample_index")
            if isinstance(slot_index, int):
                state["slots"] = max(state["slots"], slot_index + 1)
            else:
                state["slots"] = state["requests"]
            if str(sample.get("status")) != "success":
                state["failures"] += 1
                self._failed_samples += 1

        self._completed_slots = sum(
            int(state.get("slots", 0)) for state in self._live_state.values()
        )
        if self._expected_samples > 0:
            percent = min(
                100,
                int(100 * self._completed_slots / self._expected_samples),
            )
            self.progress.setValue(percent)
            self.cards["progress"].update_card(
                f"{percent}%",
                f"{self._completed_slots} of {self._expected_samples} slots",
            )
        self.cards["samples"].update_card(
            str(self._completed_slots),
            f"{self._received_samples} requests",
        )
        self.cards["failures"].update_card(str(self._failed_samples))
        self.cards["failures"].set_value_color(
            COLORS["danger"] if self._failed_samples else COLORS["text"]
        )
        self._refresh_run_table()

    def _on_stage(self, ammeter_type: str, stage: str) -> None:
        state = self._live_state.setdefault(
            ammeter_type,
            {
                "stage": stage,
                "slots": 0,
                "requests": 0,
                "failures": 0,
                "mean": None,
                "status": "",
            },
        )
        state["stage"] = stage
        self._refresh_run_table()

    def _on_analysis(
        self,
        ammeter_type: str,
        analysis: Mapping[str, Any],
    ) -> None:
        self._analyses[ammeter_type] = dict(analysis)
        retried = sum(
            count_retried_samples(entry)
            for entry in self._analyses.values()
        )
        self.cards["retried"].update_card(str(retried))
        self.cards["retried"].set_value_color(
            COLORS["warning"] if retried else COLORS["text"]
        )
        statistics = analysis.get("statistics") or {}
        state = self._live_state.setdefault(ammeter_type, {})
        state["mean"] = statistics.get("mean_current")
        state["status"] = str(analysis.get("status", ""))
        self.cards["mean"].update_card(
            format_number(statistics.get("mean_current"), digits=5, suffix=" A"),
            title_case(ammeter_type),
        )
        self._refresh_run_table()

    def _on_completed(self, outcome: Mapping[str, Any]) -> None:
        failures = dict(outcome.get("failures") or {})
        archived = dict(outcome.get("archived_runs") or {})
        cancelled = bool(outcome.get("cancelled"))
        self.cards["archived"].update_card(str(len(archived)))
        self.progress.setValue(
            100 if not cancelled and not failures else self.progress.value()
        )
        self.cards["progress"].update_card(
            "Stopped" if cancelled else "Complete",
            "",
            emphasis=False,
        )

        if failures:
            detail = "; ".join(
                f"{title_case(name)}: {message}"
                for name, message in failures.items()
            )
            self.banner.show_message(f"Run finished with errors — {detail}")
        elif cancelled:
            self.banner.show_message(
                "Run stopped early. Completed ammeters were analyzed and "
                "archived; the interrupted window was discarded.",
                "warning",
            )
        else:
            self.banner.show_message(
                f"Run complete — {len(self._analyses)} analyzed, "
                f"{len(archived)} archived.",
                "success",
            )
        self.run_completed.emit(dict(outcome))
        self.message.emit(
            "Run stopped" if cancelled else "Run complete",
            "warning" if cancelled or failures else "success",
        )

    def _on_failed(self, message: str, traceback_text: str) -> None:
        self.banner.show_message(f"Run failed — {message}", "error")
        self.banner.setToolTip(traceback_text)
        self.cards["progress"].update_card("Failed", "", emphasis=False)

    def _on_thread_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self._stop_token = None
        self._set_busy(False)

    def _refresh_run_table(self) -> None:
        rows = []
        for name, state in self._live_state.items():
            stage = str(state.get("stage", "queued"))
            status = str(state.get("status", "")) or stage
            rows.append(
                [
                    table_item(title_case(name)),
                    table_item(STAGE_LABELS.get(stage, title_case(stage))),
                    table_item(
                        str(state.get("slots", 0)),
                        sort_value=state.get("slots", 0),
                        align_right=True,
                        tooltip=(
                            f"{state.get('requests', 0)} requests issued"
                        ),
                    ),
                    table_item(
                        str(state.get("failures", 0)),
                        sort_value=state.get("failures", 0),
                        align_right=True,
                        color=(
                            COLORS["danger"]
                            if state.get("failures")
                            else None
                        ),
                    ),
                    table_item(
                        format_number(state.get("mean"), digits=5),
                        align_right=True,
                        monospace=True,
                    ),
                    table_item(
                        title_case(status),
                        color=status_color(state.get("status") or ""),
                    ),
                ]
            )
        fill_table(self.run_table, rows)

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _restore_settings(self) -> None:
        stored_count = self._settings.value("run/measurements_count")
        stored_frequency = self._settings.value("run/sampling_frequency_hz")
        try:
            if stored_count is not None:
                self.count_input.setValue(int(stored_count))
            if stored_frequency is not None:
                self.frequency_input.setValue(float(stored_frequency))
        except (TypeError, ValueError):
            pass
        archive = self._settings.value("run/archive_results")
        if archive is not None:
            self.archive_toggle.setChecked(str(archive).lower() == "true")
        selected = self._settings.value("run/selected_ammeters")
        if isinstance(selected, str):
            selected = [selected]
        if isinstance(selected, list) and selected:
            for name, checkbox in self._ammeter_checks.items():
                checkbox.setChecked(name in selected)

    def _save_settings(self) -> None:
        self._settings.setValue(
            "run/measurements_count",
            self.count_input.value(),
        )
        self._settings.setValue(
            "run/sampling_frequency_hz",
            self.frequency_input.value(),
        )
        self._settings.setValue(
            "run/archive_results",
            "true" if self.archive_toggle.isChecked() else "false",
        )
        self._settings.setValue(
            "run/selected_ammeters",
            list(self._selected_ammeters()),
        )

    def latest_summary_cards(self) -> List[Dict[str, str]]:
        """Expose the most recent analysis summary for reuse in tests."""
        if not self._analyses:
            return []
        latest = list(self._analyses.values())[-1]
        return build_summary_cards(latest)
