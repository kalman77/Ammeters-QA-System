from typing import Iterable

from src.domain.models.archived_test_run import ArchivedTestRun
from src.presentation.console.format_archived_test_runs_table import (
    format_archived_test_runs_table,
)


def print_archived_test_runs(
    archived_runs: Iterable[ArchivedTestRun],
) -> None:
    """Print archived test runs as one aligned console table."""
    print(format_archived_test_runs_table(archived_runs))
