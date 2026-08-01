from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.archived_test_run import MAX_METADATA_ENTRIES
from src.domain.models.run_metadata_entry import RunMetadataEntry


MAX_ARCHIVE_QUERY_LIMIT = 10_000


@dataclass(frozen=True)
class ArchivedRunQuery:
    """Validated immutable filters for historical archive retrieval."""

    ammeter_type: Optional[str]
    status: Optional[MeasurementStatus]
    archived_from_utc: Optional[datetime]
    archived_until_utc: Optional[datetime]
    metadata: Tuple[RunMetadataEntry, ...]
    has_statistics: Optional[bool]
    limit: Optional[int]

    def __post_init__(self) -> None:
        if self.ammeter_type is not None and (
            not isinstance(self.ammeter_type, str)
            or not self.ammeter_type
            or self.ammeter_type != self.ammeter_type.strip().lower()
        ):
            raise ValueError(
                "ammeter_type must be a normalized non-empty string or None"
            )
        if self.status is not None and not isinstance(
            self.status,
            MeasurementStatus,
        ):
            raise ValueError("status must be MeasurementStatus or None")
        for field_name, value in (
            ("archived_from_utc", self.archived_from_utc),
            ("archived_until_utc", self.archived_until_utc),
        ):
            if value is not None and (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() != timedelta(0)
            ):
                raise ValueError(
                    f"{field_name} must be timezone-aware UTC or None"
                )
        if (
            self.archived_from_utc is not None
            and self.archived_until_utc is not None
            and self.archived_from_utc > self.archived_until_utc
        ):
            raise ValueError(
                "archived_from_utc cannot follow archived_until_utc"
            )
        if (
            not isinstance(self.metadata, tuple)
            or len(self.metadata) > MAX_METADATA_ENTRIES
            or not all(
                isinstance(entry, RunMetadataEntry)
                for entry in self.metadata
            )
        ):
            raise ValueError(
                "metadata must be a tuple containing no more than "
                f"{MAX_METADATA_ENTRIES} RunMetadataEntry values"
            )
        metadata_keys = tuple(entry.key for entry in self.metadata)
        if (
            len(set(metadata_keys)) != len(metadata_keys)
            or metadata_keys != tuple(sorted(metadata_keys))
        ):
            raise ValueError(
                "query metadata keys must be unique and sorted"
            )
        if self.has_statistics is not None and not isinstance(
            self.has_statistics,
            bool,
        ):
            raise ValueError("has_statistics must be a boolean or None")
        if self.limit is not None and (
            isinstance(self.limit, bool)
            or not isinstance(self.limit, int)
            or self.limit < 1
            or self.limit > MAX_ARCHIVE_QUERY_LIMIT
        ):
            raise ValueError(
                "limit must be a positive integer no greater than "
                f"{MAX_ARCHIVE_QUERY_LIMIT}, or None"
            )
