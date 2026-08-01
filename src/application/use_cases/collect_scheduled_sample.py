from src.application.errors.invalid_measurement_error import (
    InvalidMeasurementError,
)
from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.application.ports.ammeter_client import AmmeterClient
from src.application.ports.monotonic_clock import MonotonicClock
from src.application.ports.running_emulator import RunningEmulator
from src.application.ports.sleeper import Sleeper
from src.application.ports.utc_clock import UtcClock
from src.application.use_cases.measure_running_ammeter import (
    measure_running_ammeter,
)
from src.application.use_cases.wait_until_deadline import (
    wait_until_deadline,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.network_settings import NetworkSettings
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_settings import SamplingSettings


def collect_scheduled_sample(
    running_emulator: RunningEmulator,
    network_settings: NetworkSettings,
    sampling_settings: SamplingSettings,
    sample_index: int,
    sampling_origin: float,
    *,
    request_current: AmmeterClient,
    monotonic_clock: MonotonicClock,
    utc_clock: UtcClock,
    sleeper: Sleeper,
) -> SampleResult:
    """Collect one fixed-deadline slot without issuing catch-up requests."""
    scheduled_elapsed = (
        float(sample_index) / sampling_settings.sampling_frequency_hz
    )
    slot_period = 1.0 / sampling_settings.sampling_frequency_hz
    deadline = sampling_origin + scheduled_elapsed
    slot_end = deadline + slot_period
    started_at = wait_until_deadline(
        deadline,
        slot_end,
        monotonic_clock=monotonic_clock,
        sleeper=sleeper,
    )

    if started_at is None:
        completed_elapsed = max(
            0.0,
            monotonic_clock() - sampling_origin,
        )
        error = MeasurementError(
            code=MeasurementErrorCode.SAMPLING_SLOT_MISSED,
            message=(
                f"Sampling slot {sample_index} at "
                f"{scheduled_elapsed:.6f}s was missed"
            ),
        )
        return SampleResult(
            sample_index=sample_index,
            scheduled_elapsed_seconds=scheduled_elapsed,
            started_elapsed_seconds=None,
            completed_elapsed_seconds=completed_elapsed,
            result=MeasurementResult(
                ammeter_type=running_emulator.settings.name,
                status=MeasurementStatus.FAILED,
                timestamp_utc=utc_clock(),
                elapsed_seconds=0.0,
                current=None,
                unit="A",
                request_latency_seconds=None,
                errors=(error,),
            ),
        )

    started_elapsed = max(0.0, started_at - sampling_origin)
    try:
        measurement = measure_running_ammeter(
            running_emulator,
            network_settings,
            request_current=request_current,
            monotonic_clock=monotonic_clock,
            utc_clock=utc_clock,
        )
    except MeasurementRequestError as exc:
        completed_elapsed = max(
            started_elapsed,
            monotonic_clock() - sampling_origin,
        )
        error = MeasurementError(
            code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
            message=str(exc) or "Measurement request failed",
        )
        result = MeasurementResult(
            ammeter_type=running_emulator.settings.name,
            status=MeasurementStatus.FAILED,
            timestamp_utc=utc_clock(),
            elapsed_seconds=completed_elapsed - started_elapsed,
            current=None,
            unit="A",
            request_latency_seconds=None,
            errors=(error,),
        )
    except InvalidMeasurementError as exc:
        completed_elapsed = max(
            started_elapsed,
            monotonic_clock() - sampling_origin,
        )
        error = MeasurementError(
            code=MeasurementErrorCode.INVALID_MEASUREMENT,
            message=str(exc) or "Measurement was invalid",
        )
        result = MeasurementResult(
            ammeter_type=running_emulator.settings.name,
            status=MeasurementStatus.FAILED,
            timestamp_utc=utc_clock(),
            elapsed_seconds=completed_elapsed - started_elapsed,
            current=None,
            unit="A",
            request_latency_seconds=None,
            errors=(error,),
        )
    else:
        completed_elapsed = max(
            started_elapsed,
            monotonic_clock() - sampling_origin,
        )
        result = MeasurementResult(
            ammeter_type=measurement.ammeter_type,
            status=MeasurementStatus.SUCCESS,
            timestamp_utc=measurement.timestamp_utc,
            elapsed_seconds=completed_elapsed - started_elapsed,
            current=measurement.current,
            unit=measurement.unit,
            request_latency_seconds=measurement.request_latency_seconds,
            errors=(),
        )

    return SampleResult(
        sample_index=sample_index,
        scheduled_elapsed_seconds=scheduled_elapsed,
        started_elapsed_seconds=started_elapsed,
        completed_elapsed_seconds=completed_elapsed,
        result=result,
    )
