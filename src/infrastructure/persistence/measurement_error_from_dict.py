from collections.abc import Mapping

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.models.measurement_error import MeasurementError


def measurement_error_from_dict(data: object) -> MeasurementError:
    """Reconstruct one typed measurement error from archive data."""
    if not isinstance(data, Mapping):
        raise ValueError("measurement error must be a mapping")
    return MeasurementError(
        code=MeasurementErrorCode(data["code"]),
        message=data["message"],
    )
