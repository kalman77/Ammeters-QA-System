from src.application.errors.ammeter_framework_error import (
    AmmeterFrameworkError,
)


class UnsupportedAmmeterError(AmmeterFrameworkError, ValueError):
    """Raised when no configured ammeter matches the requested type."""
