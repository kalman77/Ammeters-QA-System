from src.application.errors.ammeter_framework_error import (
    AmmeterFrameworkError,
)


class SamplingConfigurationError(AmmeterFrameworkError, ValueError):
    """Raised when a sampling window cannot be resolved safely."""
