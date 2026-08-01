from src.application.errors.invalid_ammeter_type_error import (
    InvalidAmmeterTypeError,
)


def normalize_ammeter_type(ammeter_type: object) -> str:
    """Validate and normalize a public ammeter selector."""
    if not isinstance(ammeter_type, str):
        raise InvalidAmmeterTypeError(
            "ammeter_type must be a non-empty string"
        )

    normalized = ammeter_type.strip().lower()
    if not normalized:
        raise InvalidAmmeterTypeError(
            "ammeter_type must be a non-empty string"
        )

    return normalized
