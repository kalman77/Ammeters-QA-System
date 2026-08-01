from functools import partial
from pathlib import Path
from typing import Any, Mapping, Union

from src.application.ports.utc_clock import UtcClock
from src.infrastructure.config.read_result_archive_directory import (
    read_result_archive_directory,
)
from src.infrastructure.identifiers.generate_run_id import generate_run_id
from src.infrastructure.persistence.list_archived_test_runs import (
    list_archived_test_runs,
)
from src.infrastructure.persistence.load_archived_test_run import (
    load_archived_test_run,
)
from src.infrastructure.persistence.save_archived_test_run import (
    save_archived_test_run,
)
from src.testing.ammeter_result_manager import AmmeterResultManager


def build_ammeter_result_manager(
    config: Mapping[str, Any],
    config_path: Union[str, Path],
    utc_clock: UtcClock,
) -> AmmeterResultManager:
    """Compose the default lazy Phase 5 result manager."""
    archive_directory = read_result_archive_directory(
        config,
        config_path,
    )
    return AmmeterResultManager(
        save_archived_run=partial(
            save_archived_test_run,
            archive_directory,
        ),
        load_archived_run=partial(
            load_archived_test_run,
            archive_directory,
        ),
        list_archived_runs=partial(
            list_archived_test_runs,
            archive_directory,
        ),
        generate_run_id=generate_run_id,
        utc_clock=utc_clock,
    )
