from typing import Optional

from src.application.errors.sampling_configuration_error import (
    SamplingConfigurationError,
)
from src.domain.models.retry_policy import RetryPolicy


def resolve_retry_policy(
    max_attempts: Optional[object],
    retry_delay_seconds: Optional[object],
) -> RetryPolicy:
    """Validate optional retry inputs and build a bounded retry policy."""
    resolved_attempts = 1 if max_attempts is None else max_attempts
    resolved_delay = (
        0.0 if retry_delay_seconds is None else retry_delay_seconds
    )
    try:
        policy = RetryPolicy(
            max_attempts=resolved_attempts,
            retry_delay_seconds=resolved_delay,
        )
    except ValueError as exc:
        raise SamplingConfigurationError(str(exc)) from exc
    if policy.max_attempts == 1 and policy.retry_delay_seconds > 0:
        raise SamplingConfigurationError(
            "retry_delay_seconds requires max_attempts greater than 1"
        )
    return policy
