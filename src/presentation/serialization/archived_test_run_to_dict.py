from typing import Any, Dict

from src.domain.models.archived_test_run import ArchivedTestRun
from src.infrastructure.persistence.archive_schema_version import (
    ARCHIVE_SCHEMA_VERSION,
)
from src.infrastructure.persistence.archived_test_run_to_archive_dict import (
    archived_test_run_to_archive_dict,
)


def archived_test_run_to_dict(
    archived_run: ArchivedTestRun,
) -> Dict[str, Any]:
    """Serialize one versioned archived run with complete provenance."""
    return archived_test_run_to_archive_dict(archived_run)
