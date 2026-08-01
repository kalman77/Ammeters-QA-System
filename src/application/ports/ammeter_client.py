from typing import Protocol


class AmmeterClient(Protocol):
    """Callable port for retrieving one current measurement."""

    def __call__(
        self,
        port: int,
        command: bytes,
        *,
        host: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
    ) -> float:
        ...
