from typing import Protocol

from src.domain.models.archived_test_run import ArchivedTestRun


class ArchivedRunSaver(Protocol):
    """Persist one append-only archived test run."""

    def __call__(self, archived_run: ArchivedTestRun) -> None:
        ...
