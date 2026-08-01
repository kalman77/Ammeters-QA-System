from src.application.ports.ammeter_client import AmmeterClient
from src.application.ports.monotonic_clock import MonotonicClock
from src.application.ports.running_emulator import RunningEmulator
from src.application.ports.utc_clock import UtcClock
from src.domain.models.measurement import Measurement
from src.domain.models.network_settings import NetworkSettings
from src.application.use_cases.validate_current import validate_current


def measure_running_ammeter(
    running_emulator: RunningEmulator,
    network_settings: NetworkSettings,
    *,
    request_current: AmmeterClient,
    monotonic_clock: MonotonicClock,
    utc_clock: UtcClock,
) -> Measurement:
    """Request and validate one reading from an already-running emulator."""
    request_started = monotonic_clock()
    current = validate_current(
        request_current(
            running_emulator.emulator.port,
            running_emulator.settings.command,
            host=network_settings.host,
            connect_timeout_seconds=(
                network_settings.connect_timeout_seconds
            ),
            read_timeout_seconds=network_settings.read_timeout_seconds,
        )
    )
    request_latency = max(0.0, monotonic_clock() - request_started)

    return Measurement(
        ammeter_type=running_emulator.settings.name,
        current=current,
        unit="A",
        timestamp_utc=utc_clock(),
        request_latency_seconds=request_latency,
    )
