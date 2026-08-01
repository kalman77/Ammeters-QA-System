from src.application.errors.result_management_error import (
    ResultManagementError,
)


class InvalidRunMetadataError(ResultManagementError, ValueError):
    """Raised when archive metadata is not valid and JSON-safe."""
