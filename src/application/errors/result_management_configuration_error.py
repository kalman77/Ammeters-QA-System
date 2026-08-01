from src.application.errors.result_management_error import (
    ResultManagementError,
)


class ResultManagementConfigurationError(ResultManagementError, ValueError):
    """Raised when lazy archive configuration is missing or invalid."""
