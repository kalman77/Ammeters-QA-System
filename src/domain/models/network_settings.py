from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkSettings:
    """Network timing and host settings used by emulator sessions."""

    host: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    startup_timeout_seconds: float
    shutdown_timeout_seconds: float
