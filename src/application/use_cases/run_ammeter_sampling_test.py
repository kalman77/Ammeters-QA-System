import threading
from typing import List, Optional

from src.application.errors.emulator_start_error import EmulatorStartError
from src.application.errors.emulator_stop_error import EmulatorStopError
from src.application.ports.ammeter_client import AmmeterClient
from src.application.ports.emulator_starter import EmulatorStarter
from src.application.ports.emulator_stopper import EmulatorStopper
from src.application.ports.monotonic_clock import MonotonicClock
from src.application.ports.running_emulator import RunningEmulator
from src.application.ports.sleeper import Sleeper
from src.application.ports.utc_clock import UtcClock
from src.application.use_cases.collect_scheduled_sample import (
    collect_scheduled_sample,
)
from src.application.use_cases.normalize_ammeter_type import (
    normalize_ammeter_type,
)
from src.application.use_cases.select_ammeter_settings import (
    select_ammeter_settings,
)
from src.application.use_cases.wait_until_deadline import (
    wait_until_deadline,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.runtime_settings import RuntimeSettings
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings


def run_ammeter_sampling_test(
    runtime_settings: RuntimeSettings,
    sampling_settings: SamplingSettings,
    ammeter_type: object,
    *,
    start_emulators: EmulatorStarter,
    stop_emulators: EmulatorStopper,
    request_current: AmmeterClient,
    monotonic_clock: MonotonicClock,
    utc_clock: UtcClock,
    sleeper: Sleeper,
) -> SamplingResult:
    """Run one fixed-deadline sampling window for a selected ammeter."""
    normalized_type = normalize_ammeter_type(ammeter_type)
    selected_settings = select_ammeter_settings(
        runtime_settings,
        normalized_type,
    )
    selected_runtime = RuntimeSettings(
        network=runtime_settings.network,
        ammeters=(selected_settings,),
    )
    operation_started = monotonic_clock()
    stop_event = threading.Event()
    running_emulators: List[RunningEmulator] = []
    samples: List[SampleResult] = []
    errors: List[MeasurementError] = []
    sampling_origin: Optional[float] = None
    sampling_started_at_utc = None
    sampling_elapsed_seconds: Optional[float] = None

    try:
        try:
            running_emulators = start_emulators(
                selected_runtime,
                stop_event,
            )
        except EmulatorStartError as exc:
            errors.append(
                MeasurementError(
                    code=MeasurementErrorCode.EMULATOR_START_FAILED,
                    message=str(exc) or "Emulator startup failed",
                )
            )
        else:
            if (
                len(running_emulators) != 1
                or running_emulators[0].settings.name != normalized_type
            ):
                errors.append(
                    MeasurementError(
                        code=MeasurementErrorCode.EMULATOR_START_FAILED,
                        message=(
                            "Emulator starter did not return exactly the "
                            f"requested {normalized_type!r} emulator"
                        ),
                    )
                )
            else:
                sampling_origin = monotonic_clock()
                sampling_started_at_utc = utc_clock()
                for sample_index in range(
                    sampling_settings.measurements_count
                ):
                    samples.append(
                        collect_scheduled_sample(
                            running_emulators[0],
                            runtime_settings.network,
                            sampling_settings,
                            sample_index,
                            sampling_origin,
                            request_current=request_current,
                            monotonic_clock=monotonic_clock,
                            utc_clock=utc_clock,
                            sleeper=sleeper,
                        )
                    )

                sampling_window_end = (
                    sampling_origin
                    + sampling_settings.total_duration_seconds
                )
                window_completed_at = wait_until_deadline(
                    sampling_window_end,
                    float("inf"),
                    monotonic_clock=monotonic_clock,
                    sleeper=sleeper,
                )
                sampling_elapsed_seconds = max(
                    0.0,
                    window_completed_at - sampling_origin,
                )
    finally:
        if running_emulators:
            try:
                stop_emulators(
                    running_emulators,
                    stop_event,
                    runtime_settings.network.shutdown_timeout_seconds,
                )
            except EmulatorStopError as exc:
                errors.append(
                    MeasurementError(
                        code=MeasurementErrorCode.EMULATOR_STOP_FAILED,
                        message=str(exc) or "Emulator shutdown failed",
                    )
                )

    successful_samples = sum(
        sample.result.status is MeasurementStatus.SUCCESS
        for sample in samples
    )
    has_failures = bool(errors) or successful_samples != len(samples)
    if (
        successful_samples == sampling_settings.measurements_count
        and not has_failures
    ):
        status = MeasurementStatus.SUCCESS
    elif successful_samples:
        status = MeasurementStatus.PARTIAL
    else:
        status = MeasurementStatus.FAILED

    return SamplingResult(
        ammeter_type=normalized_type,
        status=status,
        timestamp_utc=utc_clock(),
        elapsed_seconds=max(
            0.0,
            monotonic_clock() - operation_started,
        ),
        sampling_started_at_utc=sampling_started_at_utc,
        sampling_elapsed_seconds=sampling_elapsed_seconds,
        settings=sampling_settings,
        samples=tuple(samples),
        errors=tuple(errors),
        unit="A",
    )
