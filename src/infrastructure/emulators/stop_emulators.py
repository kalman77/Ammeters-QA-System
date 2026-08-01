import threading
from typing import Sequence

from src.application.errors.emulator_stop_error import EmulatorStopError
from src.infrastructure.emulators.join_emulator_threads import (
    join_emulator_threads,
)
from src.infrastructure.emulators.running_emulator import RunningEmulator


def stop_emulators(
    running_emulators: Sequence[RunningEmulator],
    stop_event: threading.Event,
    timeout_seconds: float,
) -> None:
    """Signal all emulators, join them, and reject thread leaks."""
    stop_event.set()
    still_running = join_emulator_threads(
        running_emulators,
        timeout_seconds,
    )
    if still_running:
        names = ", ".join(still_running)
        raise EmulatorStopError(
            f"Emulator threads did not stop cleanly: {names}"
        )
