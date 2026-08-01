from src.application.errors.result_management_error import (
    ResultManagementError,
)


class InvalidRunIdError(ResultManagementError, ValueError):
    """Raised when a run identifier is not a canonical UUID."""
