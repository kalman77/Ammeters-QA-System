from typing import Protocol


class RunIdGenerator(Protocol):
    """Generate one canonical unique test-run identifier."""

    def __call__(self) -> str:
        ...
