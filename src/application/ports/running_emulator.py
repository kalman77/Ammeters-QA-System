from typing import Protocol

from src.application.ports.ammeter_emulator import AmmeterEmulator
from src.domain.models.ammeter_settings import AmmeterSettings


class RunningEmulator(Protocol):
    """Application view of a running emulator."""

    settings: AmmeterSettings
    emulator: AmmeterEmulator
