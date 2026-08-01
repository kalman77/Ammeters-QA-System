from uuid import UUID


def normalize_run_id(run_id: object) -> str:
    """Return one canonical lowercase UUID string."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a canonical UUID string")
    try:
        parsed_run_id = UUID(run_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("run_id must be a canonical UUID string") from exc
    normalized_run_id = str(parsed_run_id)
    if run_id != normalized_run_id:
        raise ValueError("run_id must be a canonical UUID string")
    return normalized_run_id
