import threading
from typing import Dict, List, Optional

from src.application.ports.ammeter_client import AmmeterClient
from src.application.ports.emulator_starter import EmulatorStarter
from src.application.ports.emulator_stopper import EmulatorStopper
from src.application.ports.running_emulator import RunningEmulator
from src.domain.models.runtime_settings import RuntimeSettings


def run_ammeter_smoke_test(
    runtime_settings: RuntimeSettings,
    *,
    start_emulators: EmulatorStarter,
    stop_emulators: EmulatorStopper,
    request_current: AmmeterClient,
) -> Dict[str, float]:
    """Return one current measurement from every configured ammeter."""
    stop_event = threading.Event()
    running_emulators: List[RunningEmulator] = []
    measurements: Dict[str, float] = {}
    request_error: Optional[BaseException] = None
    network = runtime_settings.network

    try:
        running_emulators = start_emulators(
            runtime_settings,
            stop_event,
        )
        for running_emulator in running_emulators:
            measurements[
                running_emulator.settings.name
            ] = request_current(
                running_emulator.emulator.port,
                running_emulator.settings.command,
                host=network.host,
                connect_timeout_seconds=network.connect_timeout_seconds,
                read_timeout_seconds=network.read_timeout_seconds,
            )
    except BaseException as exc:
        request_error = exc
    finally:
        try:
            stop_emulators(
                running_emulators,
                stop_event,
                network.shutdown_timeout_seconds,
            )
        except BaseException as shutdown_error:
            if request_error is None:
                request_error = shutdown_error

    if request_error is not None:
        raise request_error

    return measurements
