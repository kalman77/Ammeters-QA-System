from uuid import uuid4


def generate_run_id() -> str:
    """Return a new canonical UUID suitable for an archived test run."""
    return str(uuid4())
