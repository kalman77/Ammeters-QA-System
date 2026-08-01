from dataclasses import dataclass, field
from typing import Optional

from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.current_statistics import CurrentStatistics
from src.domain.models.sampling_result import SamplingResult
from src.domain.services.calculate_current_statistics import (
    calculate_current_statistics,
)


@dataclass(frozen=True)
class SamplingAnalysis:
    """Statistical analysis paired with the sampling result it summarizes."""

    sampling_result: SamplingResult
    statistics: Optional[CurrentStatistics] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.sampling_result, SamplingResult):
            raise ValueError("sampling_result must be SamplingResult")
        currents = tuple(
            sample.result.current
            for sample in self.sampling_result.samples
            if sample.result.status is MeasurementStatus.SUCCESS
        )
        object.__setattr__(
            self,
            "statistics",
            calculate_current_statistics(currents),
        )
