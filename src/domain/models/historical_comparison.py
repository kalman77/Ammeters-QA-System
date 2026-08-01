from dataclasses import dataclass, field
from typing import Optional, Tuple

from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.models.current_statistics_delta import CurrentStatisticsDelta
from src.domain.services.calculate_current_statistics_delta import (
    calculate_current_statistics_delta,
)


@dataclass(frozen=True)
class HistoricalComparison:
    """One baseline archive compared descriptively with other archives."""

    baseline: ArchivedTestRun
    candidates: Tuple[ArchivedTestRun, ...]
    statistics_deltas: Tuple[
        Optional[CurrentStatisticsDelta],
        ...,
    ] = field(init=False)
    same_ammeter_types: Tuple[bool, ...] = field(init=False)
    same_sampling_settings: Tuple[bool, ...] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, ArchivedTestRun):
            raise ValueError("baseline must be ArchivedTestRun")
        if (
            not isinstance(self.candidates, tuple)
            or not self.candidates
            or not all(
                isinstance(candidate, ArchivedTestRun)
                for candidate in self.candidates
            )
        ):
            raise ValueError(
                "candidates must be a non-empty tuple of ArchivedTestRun"
            )
        run_ids = (
            self.baseline.run_id,
            *(candidate.run_id for candidate in self.candidates),
        )
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("historical comparison run IDs must be unique")

        object.__setattr__(
            self,
            "statistics_deltas",
            tuple(
                calculate_current_statistics_delta(
                    self.baseline.analysis.statistics,
                    candidate.analysis.statistics,
                )
                for candidate in self.candidates
            ),
        )
        baseline_sampling = self.baseline.analysis.sampling_result
        object.__setattr__(
            self,
            "same_ammeter_types",
            tuple(
                candidate.analysis.sampling_result.ammeter_type
                == baseline_sampling.ammeter_type
                for candidate in self.candidates
            ),
        )
        object.__setattr__(
            self,
            "same_sampling_settings",
            tuple(
                candidate.analysis.sampling_result.settings
                == baseline_sampling.settings
                for candidate in self.candidates
            ),
        )
