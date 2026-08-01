import threading
from dataclasses import dataclass, field
from typing import Optional

from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.domain.models.ammeter_settings import AmmeterSettings


@dataclass
class RunningEmulator:
    """Mutable process state for one running emulator thread."""

    settings: AmmeterSettings
    emulator: AmmeterEmulatorBase
    ready_event: threading.Event
    thread: threading.Thread = field(init=False)
    startup_error: Optional[BaseException] = None
