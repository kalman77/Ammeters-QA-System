import time
from typing import List, Sequence

from src.infrastructure.emulators.running_emulator import RunningEmulator


def join_emulator_threads(
    running_emulators: Sequence[RunningEmulator],
    timeout_seconds: float,
) -> List[str]:
    """Join emulator threads within one shared deadline and return leaks."""
    deadline = time.monotonic() + timeout_seconds
    for running_emulator in running_emulators:
        remaining = max(0.0, deadline - time.monotonic())
        running_emulator.thread.join(remaining)

    return [
        running_emulator.settings.name
        for running_emulator in running_emulators
        if running_emulator.thread.is_alive()
    ]
