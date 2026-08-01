from src.application.errors.unsupported_ammeter_error import (
    UnsupportedAmmeterError,
)
from src.domain.models.ammeter_settings import AmmeterSettings
from src.domain.models.runtime_settings import RuntimeSettings


def select_ammeter_settings(
    runtime_settings: RuntimeSettings,
    ammeter_type: str,
) -> AmmeterSettings:
    """Return settings for one normalized ammeter type."""
    for settings in runtime_settings.ammeters:
        if settings.name == ammeter_type:
            return settings

    supported = ", ".join(
        settings.name for settings in runtime_settings.ammeters
    )
    raise UnsupportedAmmeterError(
        f"Unsupported ammeter type {ammeter_type!r}. "
        f"Configured types: {supported}"
    )
