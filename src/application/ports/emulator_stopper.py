import threading
from typing import Protocol, Sequence

from src.application.ports.running_emulator import RunningEmulator


class EmulatorStopper(Protocol):
    """Callable port for stopping a running emulator group."""

    def __call__(
        self,
        running_emulators: Sequence[RunningEmulator],
        stop_event: threading.Event,
        timeout_seconds: float,
    ) -> None:
        ...
