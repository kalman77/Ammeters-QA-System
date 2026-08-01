from src.application.errors.ammeter_framework_error import (
    AmmeterFrameworkError,
)


class InvalidAmmeterTypeError(AmmeterFrameworkError, ValueError):
    """Raised when an ammeter selector is not a non-empty string."""
