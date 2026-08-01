import time


def read_monotonic_time() -> float:
    """Return a monotonic timestamp suitable for elapsed-time calculations."""
    return time.monotonic()
