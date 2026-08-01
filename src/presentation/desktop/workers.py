"""Background worker that runs sampling off the Qt GUI thread."""

from __future__ import annotations

import time
import traceback
from typing import Any, Dict, List, Tuple

from PySide6.QtCore import QObject, Signal

from src.presentation.desktop.run_service import (
    DesktopRunService,
    RunRequest,
    StopToken,
)


# Sampling can emit thousands of events per second; batching keeps the GUI
# thread responsive without dropping any sample.
FLUSH_INTERVAL_SECONDS = 0.05
FLUSH_BATCH_SIZE = 40


class RunWorker(QObject):
    """Execute one run request and report progress through Qt signals."""

    samples_ready = Signal(list)
    stage_changed = Signal(str, str)
    analysis_ready = Signal(str, dict)
    finished_ok = Signal(dict)
    failed = Signal(str, str)

    def __init__(
        self,
        service: DesktopRunService,
        request: RunRequest,
        stop_token: StopToken,
    ) -> None:
        super().__init__()
        self._service = service
        self._request = request
        self._stop_token = stop_token
        self._pending: List[Tuple[str, Dict[str, Any]]] = []
        self._last_flush = 0.0

    def run(self) -> None:
        """Entry point invoked once the owning thread starts."""
        self._last_flush = time.monotonic()
        try:
            outcome = self._service.execute_run(
                self._request,
                stop_token=self._stop_token,
                on_sample=self._collect_sample,
                on_stage=self._emit_stage,
                on_analysis=self._emit_analysis,
            )
        except Exception as exc:  # surfaced to the UI as a banner
            self._flush()
            self.failed.emit(
                str(exc) or type(exc).__name__,
                traceback.format_exc(),
            )
            return
        self._flush()
        self.finished_ok.emit(outcome)

    def _collect_sample(self, ammeter_type: str, sample: Dict[str, Any]) -> None:
        self._pending.append((ammeter_type, sample))
        now = time.monotonic()
        if (
            len(self._pending) >= FLUSH_BATCH_SIZE
            or now - self._last_flush >= FLUSH_INTERVAL_SECONDS
        ):
            self._last_flush = now
            self._flush()

    def _flush(self) -> None:
        if not self._pending:
            return
        batch = self._pending
        self._pending = []
        self.samples_ready.emit(batch)

    def _emit_stage(self, ammeter_type: str, stage: str) -> None:
        self._flush()
        self.stage_changed.emit(ammeter_type, stage)

    def _emit_analysis(self, ammeter_type: str, analysis: Dict[str, Any]) -> None:
        self._flush()
        self.analysis_ready.emit(ammeter_type, analysis)
