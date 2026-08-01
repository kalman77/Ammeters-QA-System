from dataclasses import dataclass

from src.domain.enums.measurement_error_code import MeasurementErrorCode


@dataclass(frozen=True)
class MeasurementError:
    """Serializable details for one operational measurement failure."""

    code: MeasurementErrorCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, MeasurementErrorCode):
            raise ValueError("measurement error code must be MeasurementErrorCode")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError(
                "measurement error message must be a non-empty string"
            )
