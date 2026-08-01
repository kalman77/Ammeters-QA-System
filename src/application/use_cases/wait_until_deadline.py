from typing import Optional

from src.application.ports.monotonic_clock import MonotonicClock
from src.application.ports.sleeper import Sleeper


def wait_until_deadline(
    deadline: float,
    slot_end: float,
    *,
    monotonic_clock: MonotonicClock,
    sleeper: Sleeper,
) -> Optional[float]:
    """Wait for a fixed slot deadline or return None if the slot expired."""
    current_time = monotonic_clock()
    if current_time >= slot_end:
        return None

    while current_time < deadline:
        sleeper(deadline - current_time)
        updated_time = monotonic_clock()
        if updated_time <= current_time:
            raise RuntimeError(
                "Sleeper returned before the monotonic clock advanced"
            )
        current_time = updated_time
        if current_time >= slot_end:
            return None

    if current_time >= slot_end:
        return None
    return current_time
