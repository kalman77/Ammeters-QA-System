import threading
import time
from typing import List, Mapping, Type

from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.application.errors.emulator_start_error import EmulatorStartError
from src.domain.models.runtime_settings import RuntimeSettings
from src.infrastructure.emulators.join_emulator_threads import (
    join_emulator_threads,
)
from src.infrastructure.emulators.running_emulator import RunningEmulator
from src.infrastructure.emulators.serve_emulator import serve_emulator


def start_emulators(
    runtime_settings: RuntimeSettings,
    stop_event: threading.Event,
    emulator_registry: Mapping[str, Type[AmmeterEmulatorBase]],
) -> List[RunningEmulator]:
    """Construct, start, and await every configured emulator."""
    running_emulators: List[RunningEmulator] = []
    network = runtime_settings.network

    try:
        for ammeter_settings in runtime_settings.ammeters:
            emulator_type = emulator_registry.get(ammeter_settings.name)
            if emulator_type is None:
                raise ValueError(
                    f"No emulator is registered for {ammeter_settings.name}"
                )

            emulator = emulator_type(
                ammeter_settings.port,
                host=network.host,
                command=ammeter_settings.command,
                request_timeout_seconds=network.read_timeout_seconds,
            )
            running_emulator = RunningEmulator(
                settings=ammeter_settings,
                emulator=emulator,
                ready_event=threading.Event(),
            )
            running_emulator.thread = threading.Thread(
                target=serve_emulator,
                args=(running_emulator, stop_event),
                name=f"ammeter-{ammeter_settings.name}",
            )
            running_emulator.thread.start()
            running_emulators.append(running_emulator)

        deadline = time.monotonic() + network.startup_timeout_seconds
        for running_emulator in running_emulators:
            remaining = deadline - time.monotonic()
            if (
                remaining <= 0
                or not running_emulator.ready_event.wait(remaining)
            ):
                raise EmulatorStartError(
                    f"Timed out starting the "
                    f"{running_emulator.settings.name} emulator"
                )
            if running_emulator.startup_error is not None:
                raise EmulatorStartError(
                    f"Unable to start the "
                    f"{running_emulator.settings.name} emulator: "
                    f"{running_emulator.startup_error}"
                ) from running_emulator.startup_error

    except BaseException as startup_error:
        stop_event.set()
        still_running = join_emulator_threads(
            running_emulators,
            network.shutdown_timeout_seconds,
        )
        if still_running:
            names = ", ".join(still_running)
            raise EmulatorStartError(
                f"Emulator startup failed and cleanup could not stop: {names}"
            ) from startup_error
        if isinstance(
            startup_error,
            (KeyboardInterrupt, SystemExit, ValueError, EmulatorStartError),
        ):
            raise
        raise EmulatorStartError(
            f"Unable to start emulator group: {startup_error}"
        ) from startup_error

    return running_emulators
