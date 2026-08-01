from datetime import datetime, timezone


def read_utc_time() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)
