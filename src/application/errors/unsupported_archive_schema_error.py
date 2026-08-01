from src.application.errors.result_management_error import (
    ResultManagementError,
)


class UnsupportedArchiveSchemaError(ResultManagementError):
    """Raised when an archive uses an unsupported persistence schema."""
