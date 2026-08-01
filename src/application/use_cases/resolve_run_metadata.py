from collections.abc import Mapping
from typing import Optional, Tuple

from src.application.errors.invalid_run_metadata_error import (
    InvalidRunMetadataError,
)
from src.domain.models.run_metadata_entry import (
    MAX_METADATA_KEY_LENGTH,
    MAX_METADATA_STRING_LENGTH,
    MetadataValue,
    RunMetadataEntry,
)
from src.domain.models.archived_test_run import MAX_METADATA_ENTRIES


def resolve_run_metadata(
    metadata: Optional[Mapping[str, MetadataValue]],
) -> Tuple[RunMetadataEntry, ...]:
    """Copy, validate, and deterministically order user archive metadata."""
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise InvalidRunMetadataError("metadata must be a mapping or None")
    if len(metadata) > MAX_METADATA_ENTRIES:
        raise InvalidRunMetadataError(
            "metadata cannot contain more than "
            f"{MAX_METADATA_ENTRIES} entries"
        )

    entries = []
    for key, value in metadata.items():
        try:
            entries.append(RunMetadataEntry(key=key, value=value))
        except ValueError as exc:
            raise InvalidRunMetadataError(str(exc)) from exc
    try:
        return tuple(sorted(entries, key=lambda entry: entry.key))
    except (TypeError, AttributeError) as exc:
        raise InvalidRunMetadataError(
            "metadata keys must be strings no longer than "
            f"{MAX_METADATA_KEY_LENGTH} characters and string values "
            f"cannot exceed {MAX_METADATA_STRING_LENGTH} characters"
        ) from exc
