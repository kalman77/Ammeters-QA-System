from src.application.errors.result_management_error import (
    ResultManagementError,
)


class InvalidArchiveQueryError(ResultManagementError, ValueError):
    """Raised when historical archive filters are invalid."""
