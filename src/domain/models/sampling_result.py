import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_settings import SamplingSettings


@dataclass(frozen=True)
class SamplingResult:
    """Aggregate result for one configured ammeter sampling window."""

    ammeter_type: str
    status: MeasurementStatus
    timestamp_utc: datetime
    elapsed_seconds: float
    sampling_started_at_utc: Optional[datetime]
    sampling_elapsed_seconds: Optional[float]
    settings: SamplingSettings
    samples: Tuple[SampleResult, ...]
    errors: Tuple[MeasurementError, ...]
    unit: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ammeter_type, str)
            or not self.ammeter_type.strip()
        ):
            raise ValueError("ammeter_type must be a non-empty string")
        if not isinstance(self.status, MeasurementStatus):
            raise ValueError("status must be MeasurementStatus")
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
        if not isinstance(self.settings, SamplingSettings):
            raise ValueError("settings must be SamplingSettings")
        if not isinstance(self.samples, tuple) or not all(
            isinstance(sample, SampleResult) for sample in self.samples
        ):
            raise ValueError("samples must be a tuple of SampleResult")
        if not isinstance(self.errors, tuple) or not all(
            isinstance(error, MeasurementError) for error in self.errors
        ):
            raise ValueError("errors must be a tuple of MeasurementError")
        if self.unit != "A":
            raise ValueError("sampling results must use unit 'A'")

        sampling_started = self.sampling_started_at_utc is not None
        if sampling_started:
            if not isinstance(self.sampling_started_at_utc, datetime) or (
                self.sampling_started_at_utc.tzinfo is None
                or self.sampling_started_at_utc.utcoffset() != timedelta(0)
            ):
                raise ValueError(
                    "sampling_started_at_utc must be timezone-aware UTC"
                )
            if (
                isinstance(self.sampling_elapsed_seconds, bool)
                or not isinstance(
                    self.sampling_elapsed_seconds,
                    (int, float),
                )
                or not math.isfinite(self.sampling_elapsed_seconds)
                or self.sampling_elapsed_seconds < 0
            ):
                raise ValueError(
                    "sampling_elapsed_seconds must be a finite "
                    "non-negative number"
                )
            if len(self.samples) != self.settings.measurements_count:
                raise ValueError(
                    "a started sampling run requires one result per slot"
                )
            if (
                self.sampling_elapsed_seconds + 1e-9
                < self.settings.total_duration_seconds
            ):
                raise ValueError(
                    "sampling elapsed time must cover the configured window"
                )
            if (
                self.samples
                and self.sampling_elapsed_seconds + 1e-9
                < max(
                    sample.completed_elapsed_seconds
                    for sample in self.samples
                )
            ):
                raise ValueError(
                    "sampling elapsed time cannot precede sample completion"
                )
            if self.elapsed_seconds + 1e-9 < self.sampling_elapsed_seconds:
                raise ValueError(
                    "operation elapsed time cannot be shorter than sampling"
                )
        elif self.sampling_elapsed_seconds is not None or self.samples:
            raise ValueError(
                "sampling timing and samples require a sampling start"
            )

        for index, sample in enumerate(self.samples):
            if sample.sample_index != index:
                raise ValueError(
                    "sample indexes must be contiguous and zero-based"
                )
            expected_offset = (
                float(index) / self.settings.sampling_frequency_hz
            )
            if not math.isclose(
                sample.scheduled_elapsed_seconds,
                expected_offset,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    "sample schedule does not match sampling frequency"
                )
            if sample.result.ammeter_type != self.ammeter_type:
                raise ValueError(
                    "sample ammeter type must match sampling result"
                )
            if sample.result.unit != self.unit:
                raise ValueError(
                    "sample unit must match sampling result unit"
                )

        successful_samples = sum(
            sample.result.status is MeasurementStatus.SUCCESS
            for sample in self.samples
        )
        has_failures = bool(self.errors) or any(
            sample.result.status is not MeasurementStatus.SUCCESS
            for sample in self.samples
        )
        if self.status is MeasurementStatus.SUCCESS:
            if (
                successful_samples != self.settings.measurements_count
                or has_failures
            ):
                raise ValueError(
                    "successful sampling requires every slot and no errors"
                )
        elif self.status is MeasurementStatus.PARTIAL:
            if successful_samples == 0 or not has_failures:
                raise ValueError(
                    "partial sampling requires measurements and failures"
                )
        elif self.status is MeasurementStatus.FAILED:
            if successful_samples != 0 or not has_failures:
                raise ValueError(
                    "failed sampling requires errors and no measurements"
                )
