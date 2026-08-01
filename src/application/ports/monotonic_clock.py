from typing import Protocol


class MonotonicClock(Protocol):
    """Callable port for elapsed-time measurements."""

    def __call__(self) -> float:
        ...
