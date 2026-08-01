import math

from src.application.errors.invalid_measurement_error import (
    InvalidMeasurementError,
)


def validate_current(current: object) -> float:
    """Return a finite current as float or raise a typed validation error."""
    if (
        isinstance(current, bool)
        or not isinstance(current, (int, float))
        or not math.isfinite(current)
    ):
        raise InvalidMeasurementError(
            "ammeter returned a current that is not a finite number"
        )

    return float(current)
