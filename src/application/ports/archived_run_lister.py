from typing import Protocol, Tuple

from src.domain.models.archived_test_run import ArchivedTestRun


class ArchivedRunLister(Protocol):
    """List all complete archived test runs in deterministic order."""

    def __call__(self) -> Tuple[ArchivedTestRun, ...]:
        ...
