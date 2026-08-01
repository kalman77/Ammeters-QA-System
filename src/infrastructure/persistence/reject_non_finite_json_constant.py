def reject_non_finite_json_constant(value: str) -> None:
    """Reject non-standard NaN and Infinity tokens in stored JSON."""
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")
