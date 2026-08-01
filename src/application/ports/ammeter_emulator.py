from typing import Protocol


class AmmeterEmulator(Protocol):
    """Minimal emulator state required by the measurement use case."""

    port: int
