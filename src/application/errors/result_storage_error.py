from src.application.errors.result_management_error import (
    ResultManagementError,
)


class ResultStorageError(ResultManagementError):
    """Raised when archive storage cannot be accessed safely."""
