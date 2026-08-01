from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Dict, Optional, Tuple

from src.application.errors.invalid_historical_comparison_error import (
    InvalidHistoricalComparisonError,
)
from src.application.ports.archived_run_lister import ArchivedRunLister
from src.application.ports.archived_run_loader import ArchivedRunLoader
from src.application.ports.archived_run_saver import ArchivedRunSaver
from src.application.ports.run_id_generator import RunIdGenerator
from src.application.ports.utc_clock import UtcClock
from src.application.use_cases.archive_sampling_analyses import (
    archive_sampling_analyses,
)
from src.application.use_cases.archive_sampling_analysis import (
    archive_sampling_analysis,
)
from src.application.use_cases.compare_archived_test_runs import (
    compare_archived_test_runs,
)
from src.application.use_cases.find_archived_test_runs import (
    find_archived_test_runs,
)
from src.application.use_cases.resolve_archived_run_query import (
    resolve_archived_run_query,
)
from src.application.use_cases.retrieve_archived_test_run import (
    retrieve_archived_test_run,
)
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.models.historical_comparison import HistoricalComparison
from src.domain.models.run_metadata_entry import MetadataValue
from src.domain.models.sampling_analysis import SamplingAnalysis


class AmmeterResultManager:
    """Public facade for archiving and reading completed analyses."""

    def __init__(
        self,
        *,
        save_archived_run: ArchivedRunSaver,
        load_archived_run: ArchivedRunLoader,
        list_archived_runs: ArchivedRunLister,
        generate_run_id: RunIdGenerator,
        utc_clock: UtcClock,
    ) -> None:
        self._save_archived_run = save_archived_run
        self._load_archived_run = load_archived_run
        self._list_archived_runs = list_archived_runs
        self._generate_run_id = generate_run_id
        self._utc_clock = utc_clock

    def archive(
        self,
        analysis: SamplingAnalysis,
        *,
        metadata: Optional[Mapping[str, MetadataValue]] = None,
    ) -> ArchivedTestRun:
        """Archive one existing analysis without running another test."""
        return archive_sampling_analysis(
            analysis,
            metadata,
            save_archived_run=self._save_archived_run,
            generate_run_id=self._generate_run_id,
            utc_clock=self._utc_clock,
        )

    def archive_all(
        self,
        analyses: Mapping[str, SamplingAnalysis],
        *,
        metadata: Optional[Mapping[str, MetadataValue]] = None,
    ) -> Dict[str, ArchivedTestRun]:
        """Archive existing analyses sequentially in mapping order."""
        return archive_sampling_analyses(
            analyses,
            metadata,
            save_archived_run=self._save_archived_run,
            generate_run_id=self._generate_run_id,
            utc_clock=self._utc_clock,
        )

    def get(self, run_id: object) -> ArchivedTestRun:
        """Retrieve one archived test run by canonical UUID."""
        return retrieve_archived_test_run(
            run_id,
            load_archived_run=self._load_archived_run,
        )

    def find(
        self,
        *,
        ammeter_type: Optional[object] = None,
        status: Optional[object] = None,
        archived_from_utc: Optional[datetime] = None,
        archived_until_utc: Optional[datetime] = None,
        metadata: Optional[Mapping[str, MetadataValue]] = None,
        has_statistics: Optional[bool] = None,
        limit: Optional[object] = None,
    ) -> Tuple[ArchivedTestRun, ...]:
        """Find historical runs using validated, combined filters."""
        query = resolve_archived_run_query(
            ammeter_type=ammeter_type,
            status=status,
            archived_from_utc=archived_from_utc,
            archived_until_utc=archived_until_utc,
            metadata=metadata,
            has_statistics=has_statistics,
            limit=limit,
        )
        return find_archived_test_runs(
            query,
            list_archived_runs=self._list_archived_runs,
        )

    def compare(
        self,
        baseline_run_id: object,
        comparison_run_ids: Iterable[object],
    ) -> HistoricalComparison:
        """Compare archived candidates against one archived baseline."""
        if isinstance(comparison_run_ids, (str, bytes)):
            raise InvalidHistoricalComparisonError(
                "comparison_run_ids must be an iterable of run IDs"
            )
        try:
            candidate_ids = tuple(comparison_run_ids)
        except TypeError as exc:
            raise InvalidHistoricalComparisonError(
                "comparison_run_ids must be an iterable of run IDs"
            ) from exc
        if not candidate_ids:
            raise InvalidHistoricalComparisonError(
                "comparison_run_ids must contain at least one run ID"
            )

        baseline = self.get(baseline_run_id)
        candidates = tuple(
            self.get(run_id) for run_id in candidate_ids
        )
        return compare_archived_test_runs(baseline, candidates)
