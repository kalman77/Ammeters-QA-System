import time


def sleep_for_seconds(seconds: float) -> None:
    """Block the current thread for a non-negative number of seconds."""
    time.sleep(seconds)
