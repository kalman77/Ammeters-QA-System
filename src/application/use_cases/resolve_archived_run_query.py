from collections.abc import Mapping
from datetime import datetime
from typing import Optional

from src.application.errors.invalid_archive_query_error import (
    InvalidArchiveQueryError,
)
from src.application.errors.invalid_run_metadata_error import (
    InvalidRunMetadataError,
)
from src.application.use_cases.resolve_run_metadata import (
    resolve_run_metadata,
)
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.archived_run_query import ArchivedRunQuery
from src.domain.models.run_metadata_entry import MetadataValue


def resolve_archived_run_query(
    *,
    ammeter_type: Optional[object] = None,
    status: Optional[object] = None,
    archived_from_utc: Optional[datetime] = None,
    archived_until_utc: Optional[datetime] = None,
    metadata: Optional[Mapping[str, MetadataValue]] = None,
    has_statistics: Optional[bool] = None,
    limit: Optional[object] = None,
) -> ArchivedRunQuery:
    """Normalize public historical-run filters into one query model."""
    if ammeter_type is None:
        normalized_ammeter_type = None
    elif not isinstance(ammeter_type, str) or not ammeter_type.strip():
        raise InvalidArchiveQueryError(
            "ammeter_type must be a non-empty string or None"
        )
    else:
        normalized_ammeter_type = ammeter_type.strip().lower()

    if status is None or isinstance(status, MeasurementStatus):
        normalized_status = status
    elif isinstance(status, str):
        try:
            normalized_status = MeasurementStatus(
                status.strip().lower()
            )
        except ValueError as exc:
            raise InvalidArchiveQueryError(
                "status must be success, partial, failed, or None"
            ) from exc
    else:
        raise InvalidArchiveQueryError(
            "status must be MeasurementStatus, string, or None"
        )

    try:
        resolved_metadata = resolve_run_metadata(metadata)
        return ArchivedRunQuery(
            ammeter_type=normalized_ammeter_type,
            status=normalized_status,
            archived_from_utc=archived_from_utc,
            archived_until_utc=archived_until_utc,
            metadata=resolved_metadata,
            has_statistics=has_statistics,
            limit=limit,
        )
    except InvalidRunMetadataError as exc:
        raise InvalidArchiveQueryError(str(exc)) from exc
    except ValueError as exc:
        raise InvalidArchiveQueryError(str(exc)) from exc
