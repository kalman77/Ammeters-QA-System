"""Desktop-facing service around the public ammeter framework.

The desktop UI never reaches past this module. Live sample streaming,
cooperative cancellation, and optional fault injection are all implemented by
decorating the ports the framework already accepts, so no domain, application,
or infrastructure module changes to support the interface.
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.domain.models.retry_policy import (
    MAX_ATTEMPTS_PER_SLOT,
    MAX_RETRY_DELAY_SECONDS,
)
from src.domain.models.sampling_settings import (
    MAX_MEASUREMENTS_COUNT,
    MAX_SAMPLING_FREQUENCY_HZ,
)
from src.infrastructure.clients.read_ammeter_current import (
    read_ammeter_current,
)
from src.infrastructure.config.default_config_path import DEFAULT_CONFIG_PATH
from src.infrastructure.config.read_result_archive_directory import (
    read_result_archive_directory,
)
from src.infrastructure.time.read_monotonic_time import read_monotonic_time
from src.presentation.serialization.archived_test_run_to_dict import (
    archived_test_run_to_dict,
)
from src.presentation.serialization.historical_comparison_to_dict import (
    historical_comparison_to_dict,
)
from src.presentation.serialization.sampling_analysis_to_dict import (
    sampling_analysis_to_dict,
)
from src.testing.test_framework import AmmeterTestFramework


SampleListener = Callable[[str, Dict[str, Any]], None]
StageListener = Callable[[str, str], None]
AnalysisListener = Callable[[str, Dict[str, Any]], None]

# Long sleeps are split into slices so a stop request is noticed promptly.
CANCELLATION_SLICE_SECONDS = 0.05


class RunCancelled(Exception):
    """Raised inside injected ports to abort a run between operations.

    The framework's sampling use case stops its emulators in a ``finally``
    block, so raising from a port unwinds without leaking listening sockets.
    """


class StopToken:
    """Thread-safe cooperative stop flag shared with the worker thread."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def request(self) -> None:
        self._event.set()

    def requested(self) -> bool:
        return self._event.is_set()

    def raise_if_requested(self) -> None:
        if self._event.is_set():
            raise RunCancelled("Run stopped by the operator")


@dataclass(frozen=True)
class FaultInjection:
    """Optional probabilistic faults applied at the client boundary."""

    enabled: bool = False
    communication_failure_probability: float = 0.0
    invalid_data_probability: float = 0.0
    outlier_probability: float = 0.0
    outlier_offset_amperes: float = 0.5
    extra_latency_probability: float = 0.0
    extra_latency_seconds: float = 0.03
    random_seed: int = 1979

    def __post_init__(self) -> None:
        for name in (
            "communication_failure_probability",
            "invalid_data_probability",
            "outlier_probability",
            "extra_latency_probability",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be a number between 0 and 1")
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        for name in ("outlier_offset_amperes", "extra_latency_seconds"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be a non-negative number")
            if float(value) < 0.0:
                raise ValueError(f"{name} must be non-negative")

    @property
    def active(self) -> bool:
        return self.enabled and any(
            (
                self.communication_failure_probability,
                self.invalid_data_probability,
                self.outlier_probability,
                self.extra_latency_probability,
            )
        )


@dataclass(frozen=True)
class RunRequest:
    """A validated snapshot of the Run page controls."""

    ammeter_types: Tuple[str, ...]
    measurements_count: int
    sampling_frequency_hz: float
    archive_results: bool = True
    max_attempts: int = 1
    retry_delay_seconds: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    faults: FaultInjection = field(default_factory=FaultInjection)

    def __post_init__(self) -> None:
        if not self.ammeter_types:
            raise ValueError("Select at least one ammeter")
        if len(set(self.ammeter_types)) != len(self.ammeter_types):
            raise ValueError("Selected ammeters must be unique")
        if (
            isinstance(self.measurements_count, bool)
            or not isinstance(self.measurements_count, int)
            or not 1 <= self.measurements_count <= MAX_MEASUREMENTS_COUNT
        ):
            raise ValueError(
                "Measurements must be an integer between 1 and "
                f"{MAX_MEASUREMENTS_COUNT}"
            )
        frequency = self.sampling_frequency_hz
        if (
            isinstance(frequency, bool)
            or not isinstance(frequency, (int, float))
            or not 0 < float(frequency) <= MAX_SAMPLING_FREQUENCY_HZ
        ):
            raise ValueError(
                "Frequency must be greater than 0 and no greater than "
                f"{MAX_SAMPLING_FREQUENCY_HZ:g} Hz"
            )
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or not 1 <= self.max_attempts <= MAX_ATTEMPTS_PER_SLOT
        ):
            raise ValueError(
                "Attempts per slot must be an integer between 1 and "
                f"{MAX_ATTEMPTS_PER_SLOT}"
            )
        delay = self.retry_delay_seconds
        if (
            isinstance(delay, bool)
            or not isinstance(delay, (int, float))
            or not 0.0 <= float(delay) <= MAX_RETRY_DELAY_SECONDS
        ):
            raise ValueError(
                "Retry delay must be between 0 and "
                f"{MAX_RETRY_DELAY_SECONDS:g} seconds"
            )
        if self.max_attempts == 1 and float(delay) > 0:
            raise ValueError(
                "A retry delay needs more than one attempt per slot"
            )
        if not isinstance(self.metadata, Mapping):
            raise ValueError("Metadata must be a mapping")

    @property
    def total_duration_seconds(self) -> float:
        """Return the window implied by N = D * F."""
        return self.measurements_count / float(self.sampling_frequency_hz)

    @property
    def total_samples(self) -> int:
        return self.measurements_count * len(self.ammeter_types)

    @property
    def retries_enabled(self) -> bool:
        return self.max_attempts > 1


class CancellableSleeper:
    """Sleeper port that slices waits so stop requests are honoured fast."""

    def __init__(self, stop_token: StopToken) -> None:
        self._stop_token = stop_token

    def __call__(self, seconds: float) -> None:
        self._stop_token.raise_if_requested()
        remaining = float(seconds)
        while remaining > 0.0:
            slice_seconds = min(remaining, CANCELLATION_SLICE_SECONDS)
            time.sleep(slice_seconds)
            remaining -= slice_seconds
            self._stop_token.raise_if_requested()


class LiveAmmeterClient:
    """Ammeter client port that streams samples and can inject faults."""

    def __init__(
        self,
        *,
        port_to_ammeter: Mapping[int, str],
        stop_token: StopToken,
        faults: FaultInjection,
        on_sample: Optional[SampleListener] = None,
        delegate: Callable[..., float] = read_ammeter_current,
        monotonic_clock: Callable[[], float] = read_monotonic_time,
    ) -> None:
        self._port_to_ammeter = dict(port_to_ammeter)
        self._stop_token = stop_token
        self._faults = faults
        self._on_sample = on_sample
        self._delegate = delegate
        self._monotonic_clock = monotonic_clock
        self._random = random.Random(faults.random_seed)
        self._origin = monotonic_clock()
        self._index = 0

    def begin_ammeter(self) -> None:
        """Reset the per-ammeter sample counter and elapsed-time origin."""
        self._origin = self._monotonic_clock()
        self._index = 0

    def __call__(
        self,
        port: int,
        command: bytes,
        *,
        host: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
    ) -> float:
        self._stop_token.raise_if_requested()
        ammeter_type = self._port_to_ammeter.get(int(port), str(port))
        index = self._index
        self._index += 1
        started = self._monotonic_clock()

        try:
            value = self._read(
                port,
                command,
                host=host,
                connect_timeout_seconds=connect_timeout_seconds,
                read_timeout_seconds=read_timeout_seconds,
            )
        except Exception as exc:  # re-raised after the UI is told
            if not isinstance(exc, RunCancelled):
                self._emit(
                    ammeter_type,
                    index,
                    started,
                    value=None,
                    error=str(exc) or type(exc).__name__,
                )
            raise
        self._emit(ammeter_type, index, started, value=value, error=None)
        return value

    def _read(
        self,
        port: int,
        command: bytes,
        *,
        host: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
    ) -> float:
        faults = self._faults
        if faults.active:
            if self._triggered(faults.extra_latency_probability):
                time.sleep(float(faults.extra_latency_seconds))
                self._stop_token.raise_if_requested()
            if self._triggered(faults.communication_failure_probability):
                raise MeasurementRequestError(
                    "Injected communication failure"
                )
            if self._triggered(faults.invalid_data_probability):
                return float("nan")

        value = self._delegate(
            port,
            command,
            host=host,
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
        )
        if faults.active and self._triggered(faults.outlier_probability):
            return float(value) + float(faults.outlier_offset_amperes)
        return value

    def _triggered(self, probability: float) -> bool:
        return probability > 0.0 and self._random.random() < probability

    def _emit(
        self,
        ammeter_type: str,
        index: int,
        started: float,
        *,
        value: Optional[float],
        error: Optional[str],
    ) -> None:
        if self._on_sample is None:
            return
        # A returned value the framework will reject counts as a failure here
        # too, so the live counters match the archived analysis.
        if error is None:
            try:
                usable = value is not None and math.isfinite(float(value))
            except (TypeError, ValueError):
                usable = False
            if not usable:
                error = "Invalid measurement value"
        completed = self._monotonic_clock()
        self._on_sample(
            ammeter_type,
            {
                "sample_index": index,
                "elapsed_seconds": max(0.0, started - self._origin),
                "latency_seconds": max(0.0, completed - started),
                "current": value,
                "status": "failed" if error is not None else "success",
                "error": error,
            },
        )


class DesktopRunService:
    """Own the framework instances the desktop pages drive."""

    def __init__(
        self,
        config_path: Union[str, Path] = DEFAULT_CONFIG_PATH,
    ) -> None:
        self.config_path = Path(config_path).absolute()
        self._reader = AmmeterTestFramework(self.config_path)

    @property
    def config(self) -> Mapping[str, Any]:
        return self._reader.config

    @property
    def ammeter_types(self) -> Tuple[str, ...]:
        return self._reader.ammeter_types

    @property
    def archive_directory(self) -> Path:
        return read_result_archive_directory(
            self._reader.config,
            self.config_path,
        )

    def default_sampling(self) -> Dict[str, Any]:
        """Return the configured sampling window, falling back safely."""
        try:
            settings = self._reader.sampling_settings
        except Exception:
            return {
                "measurements_count": 20,
                "total_duration_seconds": 4.0,
                "sampling_frequency_hz": 5.0,
            }
        return {
            "measurements_count": settings.measurements_count,
            "total_duration_seconds": settings.total_duration_seconds,
            "sampling_frequency_hz": settings.sampling_frequency_hz,
        }

    def retry_defaults(self) -> Dict[str, Any]:
        """Return the configured retry policy, falling back to no retries."""
        try:
            policy = self._reader.retry_policy
        except Exception:
            return {"max_attempts": 1, "retry_delay_seconds": 0.0}
        return {
            "max_attempts": policy.max_attempts,
            "retry_delay_seconds": policy.retry_delay_seconds,
        }

    def port_map(self) -> Dict[int, str]:
        """Map configured emulator ports back to ammeter names."""
        ammeters = self._reader.config.get("ammeters")
        ports: Dict[int, str] = {}
        if isinstance(ammeters, Mapping):
            for name, settings in ammeters.items():
                if isinstance(settings, Mapping):
                    port = settings.get("port")
                    if isinstance(port, int) and not isinstance(port, bool):
                        ports[port] = str(name).lower()
        return ports

    def execute_run(
        self,
        request: RunRequest,
        *,
        stop_token: StopToken,
        on_sample: Optional[SampleListener] = None,
        on_stage: Optional[StageListener] = None,
        on_analysis: Optional[AnalysisListener] = None,
    ) -> Dict[str, Any]:
        """Sample, analyze, and optionally archive each selected ammeter."""
        client = LiveAmmeterClient(
            port_to_ammeter=self.port_map(),
            stop_token=stop_token,
            faults=request.faults,
            on_sample=on_sample,
        )
        framework = AmmeterTestFramework(
            self.config_path,
            request_current=client,
            sleeper=CancellableSleeper(stop_token),
        )

        analyses: Dict[str, Dict[str, Any]] = {}
        archived: Dict[str, Dict[str, Any]] = {}
        failures: Dict[str, str] = {}
        cancelled = False

        for ammeter_type in request.ammeter_types:
            if stop_token.requested():
                cancelled = True
                break
            if on_stage is not None:
                on_stage(ammeter_type, "sampling")
            client.begin_ammeter()
            try:
                analysis = framework.analyze(
                    ammeter_type,
                    measurements_count=request.measurements_count,
                    sampling_frequency_hz=float(
                        request.sampling_frequency_hz
                    ),
                    max_attempts=request.max_attempts,
                    retry_delay_seconds=(
                        float(request.retry_delay_seconds)
                        if request.max_attempts > 1
                        else None
                    ),
                )
            except RunCancelled:
                cancelled = True
                if on_stage is not None:
                    on_stage(ammeter_type, "cancelled")
                break
            except Exception as exc:
                failures[ammeter_type] = str(exc) or type(exc).__name__
                if on_stage is not None:
                    on_stage(ammeter_type, "failed")
                continue

            serialized = sampling_analysis_to_dict(analysis)
            analyses[ammeter_type] = serialized
            if on_analysis is not None:
                on_analysis(ammeter_type, serialized)

            if request.archive_results:
                if on_stage is not None:
                    on_stage(ammeter_type, "archiving")
                try:
                    archived_run = framework.results.archive(
                        analysis,
                        metadata=dict(request.metadata) or None,
                    )
                except Exception as exc:
                    failures[ammeter_type] = (
                        f"Archiving failed: {exc or type(exc).__name__}"
                    )
                else:
                    archived[ammeter_type] = archived_test_run_to_dict(
                        archived_run
                    )
            if on_stage is not None:
                on_stage(ammeter_type, "done")

        return {
            "analyses": analyses,
            "archived_runs": archived,
            "failures": failures,
            "cancelled": cancelled or stop_token.requested(),
        }

    def find_runs(
        self,
        *,
        ammeter_type: Optional[str] = None,
        status: Optional[str] = None,
        has_statistics: Optional[bool] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List archived runs, newest first, as serialized dictionaries."""
        runs = self._reader.results.find(
            ammeter_type=ammeter_type,
            status=status,
            has_statistics=has_statistics,
            limit=limit,
        )
        return [archived_test_run_to_dict(run) for run in runs]

    def get_run(self, run_id: str) -> Dict[str, Any]:
        """Retrieve one archived run by canonical UUID."""
        return archived_test_run_to_dict(self._reader.results.get(run_id))

    def compare_runs(
        self,
        baseline_run_id: str,
        candidate_run_ids: Sequence[str],
    ) -> Dict[str, Any]:
        """Compare archived candidates against one archived baseline."""
        return historical_comparison_to_dict(
            self._reader.results.compare(baseline_run_id, candidate_run_ids)
        )
