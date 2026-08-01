from collections.abc import Mapping
from typing import Dict, Optional

from src.application.ports.archived_run_saver import ArchivedRunSaver
from src.application.ports.run_id_generator import RunIdGenerator
from src.application.ports.utc_clock import UtcClock
from src.application.use_cases.archive_sampling_analysis import (
    archive_sampling_analysis,
)
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.models.run_metadata_entry import MetadataValue
from src.domain.models.sampling_analysis import SamplingAnalysis


def archive_sampling_analyses(
    analyses: Mapping[str, SamplingAnalysis],
    metadata: Optional[Mapping[str, MetadataValue]],
    *,
    save_archived_run: ArchivedRunSaver,
    generate_run_id: RunIdGenerator,
    utc_clock: UtcClock,
) -> Dict[str, ArchivedTestRun]:
    """Archive analyses sequentially in their configured mapping order."""
    if not isinstance(analyses, Mapping):
        raise ValueError("analyses must be a mapping")

    for ammeter_type, analysis in analyses.items():
        if (
            not isinstance(ammeter_type, str)
            or not isinstance(analysis, SamplingAnalysis)
            or analysis.sampling_result.ammeter_type != ammeter_type
        ):
            raise ValueError(
                "analysis keys must match SamplingAnalysis ammeter types"
            )

    archived_runs: Dict[str, ArchivedTestRun] = {}
    for ammeter_type, analysis in analyses.items():
        archived_runs[ammeter_type] = archive_sampling_analysis(
            analysis,
            metadata,
            save_archived_run=save_archived_run,
            generate_run_id=generate_run_id,
            utc_clock=utc_clock,
        )
    return archived_runs
