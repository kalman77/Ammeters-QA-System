from typing import Protocol

from src.domain.models.archived_test_run import ArchivedTestRun


class ArchivedRunLoader(Protocol):
    """Retrieve one archived test run by canonical ID."""

    def __call__(self, run_id: str) -> ArchivedTestRun:
        ...
