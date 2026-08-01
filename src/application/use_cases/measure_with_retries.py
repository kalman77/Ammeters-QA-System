from typing import Optional, Tuple

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
from src.domain.models.measurement import Measurement
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.network_settings import NetworkSettings
from src.domain.models.retry_policy import RetryPolicy


def measure_with_retries(
    running_emulator: RunningEmulator,
    network_settings: NetworkSettings,
    slot_end: float,
    retry_policy: RetryPolicy,
    *,
    request_current: AmmeterClient,
    monotonic_clock: MonotonicClock,
    utc_clock: UtcClock,
    sleeper: Sleeper,
) -> Tuple[Optional[Measurement], Optional[MeasurementError], int]:
    """Retry one slot's request inside its own window and report attempts.

    Every retry, including its backoff, must complete before ``slot_end``, so a
    recovered request can never delay or displace the next fixed deadline. The
    returned triple is the successful measurement or the last failure, plus the
    number of requests that were actually issued.
    """
    attempts = 0
    failure: Optional[MeasurementError] = None

    while True:
        attempts += 1
        try:
            measurement = measure_running_ammeter(
                running_emulator,
                network_settings,
                request_current=request_current,
                monotonic_clock=monotonic_clock,
                utc_clock=utc_clock,
            )
        except MeasurementRequestError as exc:
            failure = MeasurementError(
                code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
                message=str(exc) or "Measurement request failed",
            )
        except InvalidMeasurementError as exc:
            failure = MeasurementError(
                code=MeasurementErrorCode.INVALID_MEASUREMENT,
                message=str(exc) or "Measurement was invalid",
            )
        else:
            return measurement, None, attempts

        if attempts >= retry_policy.max_attempts:
            return None, failure, attempts
        resume_at = monotonic_clock() + retry_policy.retry_delay_seconds
        # Waiting for a deadline beyond the slot would sleep into the next
        # slot before noticing, so an unaffordable backoff is never started.
        if resume_at >= slot_end:
            return None, failure, attempts
        if (
            wait_until_deadline(
                resume_at,
                slot_end,
                monotonic_clock=monotonic_clock,
                sleeper=sleeper,
            )
            is None
        ):
            return None, failure, attempts
