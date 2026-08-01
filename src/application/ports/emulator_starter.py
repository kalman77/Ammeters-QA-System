import threading
from typing import List, Protocol

from src.application.ports.running_emulator import RunningEmulator
from src.domain.models.runtime_settings import RuntimeSettings


class EmulatorStarter(Protocol):
    """Callable port for starting a configured emulator group."""

    def __call__(
        self,
        runtime_settings: RuntimeSettings,
        stop_event: threading.Event,
    ) -> List[RunningEmulator]:
        ...
