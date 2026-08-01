from src.application.errors.result_management_error import (
    ResultManagementError,
)


class InvalidHistoricalComparisonError(ResultManagementError, ValueError):
    """Raised when historical runs cannot form a comparison."""
