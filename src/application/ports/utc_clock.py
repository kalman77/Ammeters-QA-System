from datetime import datetime
from typing import Protocol


class UtcClock(Protocol):
    """Callable port for timezone-aware UTC timestamps."""

    def __call__(self) -> datetime:
        ...
