from src.application.errors.result_management_error import (
    ResultManagementError,
)


class ArchivedRunNotFoundError(ResultManagementError, LookupError):
    """Raised when a valid run identifier is absent from the archive."""
