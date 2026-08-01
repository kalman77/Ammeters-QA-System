from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Tuple

from src.domain.models.run_metadata_entry import RunMetadataEntry
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.services.normalize_run_id import normalize_run_id


MAX_METADATA_ENTRIES = 50


@dataclass(frozen=True)
class ArchivedTestRun:
    """Append-only archived analysis with identity and user metadata."""

    run_id: str
    archived_at_utc: datetime
    analysis: SamplingAnalysis
    metadata: Tuple[RunMetadataEntry, ...]

    def __post_init__(self) -> None:
        normalize_run_id(self.run_id)
        if not isinstance(self.archived_at_utc, datetime) or (
            self.archived_at_utc.tzinfo is None
            or self.archived_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("archived_at_utc must be timezone-aware UTC")
        if not isinstance(self.analysis, SamplingAnalysis):
            raise ValueError("analysis must be SamplingAnalysis")
        if (
            not isinstance(self.metadata, tuple)
            or not all(
                isinstance(entry, RunMetadataEntry)
                for entry in self.metadata
            )
            or len(self.metadata) > MAX_METADATA_ENTRIES
        ):
            raise ValueError(
                "metadata must be a tuple containing no more than "
                f"{MAX_METADATA_ENTRIES} RunMetadataEntry values"
            )
        metadata_keys = tuple(entry.key for entry in self.metadata)
        if len(set(metadata_keys)) != len(metadata_keys):
            raise ValueError("metadata keys must be unique")
        if metadata_keys != tuple(sorted(metadata_keys)):
            raise ValueError("metadata entries must be sorted by key")
