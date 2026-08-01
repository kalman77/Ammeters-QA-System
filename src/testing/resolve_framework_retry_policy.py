from typing import Any, Mapping, Optional

from src.application.use_cases.resolve_retry_policy import (
    resolve_retry_policy,
)
from src.domain.models.retry_policy import RetryPolicy
from src.infrastructure.config.read_retry_policy import read_retry_policy


def resolve_framework_retry_policy(
    config: Mapping[str, Any],
    max_attempts: Optional[object],
    retry_delay_seconds: Optional[object],
) -> RetryPolicy:
    """Use explicit retry values or lazily read the configured policy."""
    explicit_values = (max_attempts, retry_delay_seconds)
    if any(value is not None for value in explicit_values):
        return resolve_retry_policy(*explicit_values)
    return read_retry_policy(config)
