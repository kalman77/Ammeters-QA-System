from src.application.errors.result_management_error import (
    ResultManagementError,
)


class CorruptArchivedRunError(ResultManagementError):
    """Raised when a stored archive document is malformed or contradictory."""
