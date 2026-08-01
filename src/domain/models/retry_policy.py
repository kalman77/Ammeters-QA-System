import math
from dataclasses import dataclass


MAX_ATTEMPTS_PER_SLOT = 10
MAX_RETRY_DELAY_SECONDS = 60.0


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded per-slot retry allowance for one sampling run."""

    max_attempts: int = 1
    retry_delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
            or self.max_attempts > MAX_ATTEMPTS_PER_SLOT
        ):
            raise ValueError(
                "max_attempts must be an integer between 1 and "
                f"{MAX_ATTEMPTS_PER_SLOT}"
            )
        if (
            isinstance(self.retry_delay_seconds, bool)
            or not isinstance(self.retry_delay_seconds, (int, float))
            or not math.isfinite(self.retry_delay_seconds)
            or self.retry_delay_seconds < 0
            or self.retry_delay_seconds > MAX_RETRY_DELAY_SECONDS
        ):
            raise ValueError(
                "retry_delay_seconds must be between 0 and "
                f"{MAX_RETRY_DELAY_SECONDS:g}"
            )

    @property
    def retries_enabled(self) -> bool:
        """Return whether more than one attempt per slot is permitted."""
        return self.max_attempts > 1
