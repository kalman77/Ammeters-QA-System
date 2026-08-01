import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError


@dataclass(frozen=True)
class MeasurementResult:
    """Consistent result envelope for a single ammeter test."""

    ammeter_type: str
    status: MeasurementStatus
    timestamp_utc: datetime
    elapsed_seconds: float
    current: Optional[float]
    unit: str
    request_latency_seconds: Optional[float]
    errors: Tuple[MeasurementError, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ammeter_type, str)
            or not self.ammeter_type.strip()
        ):
            raise ValueError("ammeter_type must be a non-empty string")
        if not isinstance(self.status, MeasurementStatus):
            raise ValueError("status must be MeasurementStatus")
        if not isinstance(self.errors, tuple) or not all(
            isinstance(error, MeasurementError) for error in self.errors
        ):
            raise ValueError("errors must be a tuple of MeasurementError")
        if not isinstance(self.timestamp_utc, datetime) or (
            self.timestamp_utc.tzinfo is None
            or self.timestamp_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamp_utc must be timezone-aware UTC")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not math.isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise ValueError(
                "elapsed_seconds must be a finite non-negative number"
            )
        if self.unit != "A":
            raise ValueError("measurement results must use unit 'A'")

        has_measurement = (
            self.current is not None
            and self.request_latency_seconds is not None
        )
        if self.status is MeasurementStatus.SUCCESS:
            if not has_measurement or self.errors:
                raise ValueError(
                    "successful results require a measurement and no errors"
                )
        elif self.status is MeasurementStatus.FAILED:
            if has_measurement or not self.errors:
                raise ValueError(
                    "failed results require errors and no measurement"
                )
        elif self.status is MeasurementStatus.PARTIAL:
            if not has_measurement or not self.errors:
                raise ValueError(
                    "partial results require a measurement and errors"
                )

        if has_measurement:
            if (
                isinstance(self.current, bool)
                or not isinstance(self.current, (int, float))
                or not math.isfinite(self.current)
            ):
                raise ValueError("current must be a finite number")
            if (
                isinstance(self.request_latency_seconds, bool)
                or not isinstance(
                    self.request_latency_seconds, (int, float)
                )
                or not math.isfinite(self.request_latency_seconds)
                or self.request_latency_seconds < 0
            ):
                raise ValueError(
                    "request latency must be a finite non-negative number"
                )
        elif (
            self.current is not None
            or self.request_latency_seconds is not None
        ):
            raise ValueError(
                "current and request latency must either both exist or be absent"
            )
