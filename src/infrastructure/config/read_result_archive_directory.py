from collections.abc import Mapping
from pathlib import Path
from typing import Any, Union

from src.application.errors.result_management_configuration_error import (
    ResultManagementConfigurationError,
)


def read_result_archive_directory(
    config: Mapping[str, Any],
    config_path: Union[str, Path],
) -> Path:
    """Resolve the configured archive directory without creating it."""
    if not isinstance(config, Mapping):
        raise ResultManagementConfigurationError(
            "Configuration must be a mapping"
        )
    result_management = config.get("result_management")
    if not isinstance(result_management, Mapping):
        raise ResultManagementConfigurationError(
            "Configuration must define a 'result_management' mapping"
        )

    configured_directory = result_management.get("archive_directory")
    if (
        not isinstance(configured_directory, str)
        or not configured_directory.strip()
    ):
        raise ResultManagementConfigurationError(
            "Configuration must define a non-empty "
            "'result_management.archive_directory' string"
        )

    try:
        archive_directory = Path(configured_directory.strip())
        if not archive_directory.is_absolute():
            archive_directory = (
                Path(config_path).absolute().parent / archive_directory
            )
        return archive_directory.resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ResultManagementConfigurationError(
            "Unable to resolve result archive directory"
        ) from exc
