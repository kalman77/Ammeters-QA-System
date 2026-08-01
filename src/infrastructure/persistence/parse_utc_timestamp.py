from datetime import datetime, timedelta


def parse_utc_timestamp(value: object, field_name: str) -> datetime:
    """Parse one ISO 8601 timestamp and require timezone-aware UTC."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a UTC timestamp string")
    normalized_value = (
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    try:
        parsed_value = datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be a valid ISO 8601 timestamp"
        ) from exc
    if (
        parsed_value.tzinfo is None
        or parsed_value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return parsed_value
