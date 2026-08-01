from src.application.errors.result_management_error import (
    ResultManagementError,
)


class ArchivedRunAlreadyExistsError(ResultManagementError):
    """Raised when append-only storage already contains a run ID."""
