import math
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Measurement:
    """One validated current reading from an ammeter."""

    ammeter_type: str
    current: float
    unit: str
    timestamp_utc: datetime
    request_latency_seconds: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ammeter_type, str)
            or not self.ammeter_type.strip()
        ):
            raise ValueError("ammeter_type must be a non-empty string")
        if (
            isinstance(self.current, bool)
            or not isinstance(self.current, (int, float))
            or not math.isfinite(self.current)
        ):
            raise ValueError("current must be a finite number")
        if self.unit != "A":
            raise ValueError("current measurements must use unit 'A'")
        if not isinstance(self.timestamp_utc, datetime) or (
            self.timestamp_utc.tzinfo is None
            or self.timestamp_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamp_utc must be timezone-aware UTC")
        if (
            isinstance(self.request_latency_seconds, bool)
            or not isinstance(self.request_latency_seconds, (int, float))
            or not math.isfinite(self.request_latency_seconds)
            or self.request_latency_seconds < 0
        ):
            raise ValueError(
                "request_latency_seconds must be a finite non-negative number"
            )
