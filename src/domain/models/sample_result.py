import math
from dataclasses import dataclass
from typing import Optional

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.retry_policy import MAX_ATTEMPTS_PER_SLOT


@dataclass(frozen=True)
class SampleResult:
    """Outcome and timing information for one scheduled sampling slot."""

    sample_index: int
    scheduled_elapsed_seconds: float
    started_elapsed_seconds: Optional[float]
    completed_elapsed_seconds: float
    result: MeasurementResult
    request_attempts: Optional[int] = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.sample_index, bool)
            or not isinstance(self.sample_index, int)
            or self.sample_index < 0
        ):
            raise ValueError("sample_index must be a non-negative integer")

        for field_name, value in (
            (
                "scheduled_elapsed_seconds",
                self.scheduled_elapsed_seconds,
            ),
            (
                "completed_elapsed_seconds",
                self.completed_elapsed_seconds,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(
                    f"{field_name} must be a finite non-negative number"
                )

        if self.started_elapsed_seconds is not None and (
            isinstance(self.started_elapsed_seconds, bool)
            or not isinstance(self.started_elapsed_seconds, (int, float))
            or not math.isfinite(self.started_elapsed_seconds)
            or self.started_elapsed_seconds < 0
        ):
            raise ValueError(
                "started_elapsed_seconds must be a finite non-negative "
                "number or None"
            )
        if (
            self.started_elapsed_seconds is not None
            and self.started_elapsed_seconds + 1e-9
            < self.scheduled_elapsed_seconds
        ):
            raise ValueError(
                "started_elapsed_seconds cannot precede its schedule"
            )
        if (
            self.started_elapsed_seconds is not None
            and self.completed_elapsed_seconds
            < self.started_elapsed_seconds
        ):
            raise ValueError(
                "completed_elapsed_seconds cannot precede sample start"
            )
        if (
            self.completed_elapsed_seconds + 1e-9
            < self.scheduled_elapsed_seconds
        ):
            raise ValueError(
                "completed_elapsed_seconds cannot precede its schedule"
            )
        if not isinstance(self.result, MeasurementResult):
            raise ValueError("result must be MeasurementResult")
        if self.result.status is MeasurementStatus.PARTIAL:
            raise ValueError("an individual sample cannot be partial")

        missed_slot = any(
            error.code is MeasurementErrorCode.SAMPLING_SLOT_MISSED
            for error in self.result.errors
        )
        if self.started_elapsed_seconds is None:
            if (
                self.result.status is not MeasurementStatus.FAILED
                or not missed_slot
            ):
                raise ValueError(
                    "a sample without a start time must be a missed slot"
                )
        elif missed_slot:
            raise ValueError("a missed sampling slot cannot have a start time")

        # A missed slot issues no request at all; every started slot issues at
        # least one. Omitting the count therefore has a single valid meaning.
        if self.request_attempts is None:
            object.__setattr__(
                self,
                "request_attempts",
                0 if self.started_elapsed_seconds is None else 1,
            )
        if (
            isinstance(self.request_attempts, bool)
            or not isinstance(self.request_attempts, int)
            or self.request_attempts < 0
            or self.request_attempts > MAX_ATTEMPTS_PER_SLOT
        ):
            raise ValueError(
                "request_attempts must be an integer between 0 and "
                f"{MAX_ATTEMPTS_PER_SLOT}"
            )
        if self.started_elapsed_seconds is None:
            if self.request_attempts != 0:
                raise ValueError(
                    "a missed sampling slot cannot have request attempts"
                )
        elif self.request_attempts < 1:
            raise ValueError(
                "a started sampling slot requires at least one attempt"
            )
