import threading
from typing import List, Optional

from src.application.errors.emulator_start_error import EmulatorStartError
from src.application.errors.emulator_stop_error import EmulatorStopError
from src.application.errors.invalid_measurement_error import (
    InvalidMeasurementError,
)
from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.application.ports.ammeter_client import AmmeterClient
from src.application.ports.emulator_starter import EmulatorStarter
from src.application.ports.emulator_stopper import EmulatorStopper
from src.application.ports.monotonic_clock import MonotonicClock
from src.application.ports.running_emulator import RunningEmulator
from src.application.ports.utc_clock import UtcClock
from src.application.use_cases.measure_running_ammeter import (
    measure_running_ammeter,
)
from src.application.use_cases.normalize_ammeter_type import (
    normalize_ammeter_type,
)
from src.application.use_cases.select_ammeter_settings import (
    select_ammeter_settings,
)
from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement import Measurement
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.runtime_settings import RuntimeSettings


def run_single_ammeter_test(
    runtime_settings: RuntimeSettings,
    ammeter_type: object,
    *,
    start_emulators: EmulatorStarter,
    stop_emulators: EmulatorStopper,
    request_current: AmmeterClient,
    monotonic_clock: MonotonicClock,
    utc_clock: UtcClock,
) -> MeasurementResult:
    """Run one configured ammeter and return a typed result envelope."""
    normalized_type = normalize_ammeter_type(ammeter_type)
    selected_settings = select_ammeter_settings(
        runtime_settings,
        normalized_type,
    )
    selected_runtime = RuntimeSettings(
        network=runtime_settings.network,
        ammeters=(selected_settings,),
    )
    started_at = monotonic_clock()
    stop_event = threading.Event()
    running_emulators: List[RunningEmulator] = []
    measurement: Optional[Measurement] = None
    errors: List[MeasurementError] = []

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
                try:
                    measurement = measure_running_ammeter(
                        running_emulators[0],
                        runtime_settings.network,
                        request_current=request_current,
                        monotonic_clock=monotonic_clock,
                        utc_clock=utc_clock,
                    )
                except MeasurementRequestError as exc:
                    errors.append(
                        MeasurementError(
                            code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
                            message=str(exc) or "Measurement request failed",
                        )
                    )
                except InvalidMeasurementError as exc:
                    errors.append(
                        MeasurementError(
                            code=MeasurementErrorCode.INVALID_MEASUREMENT,
                            message=str(exc) or "Measurement was invalid",
                        )
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

    if measurement is not None and errors:
        status = MeasurementStatus.PARTIAL
    elif measurement is not None:
        status = MeasurementStatus.SUCCESS
    else:
        status = MeasurementStatus.FAILED

    return MeasurementResult(
        ammeter_type=normalized_type,
        status=status,
        timestamp_utc=utc_clock(),
        elapsed_seconds=max(0.0, monotonic_clock() - started_at),
        current=measurement.current if measurement is not None else None,
        unit="A",
        request_latency_seconds=(
            measurement.request_latency_seconds
            if measurement is not None
            else None
        ),
        errors=tuple(errors),
    )
