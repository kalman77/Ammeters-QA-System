from src.application.errors.ammeter_framework_error import (
    AmmeterFrameworkError,
)


class FrameworkConfigurationError(AmmeterFrameworkError):
    """Raised when framework configuration cannot be loaded or validated."""
