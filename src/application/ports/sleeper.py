from typing import Protocol


class Sleeper(Protocol):
    """Callable port for delaying until a future sampling deadline."""

    def __call__(self, seconds: float) -> None:
        ...
