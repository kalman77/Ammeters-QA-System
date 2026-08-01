from collections.abc import Mapping
from typing import Any

from src.application.errors.sampling_configuration_error import (
    SamplingConfigurationError,
)
from src.application.use_cases.resolve_retry_policy import (
    resolve_retry_policy,
)
from src.domain.models.retry_policy import RetryPolicy


def read_retry_policy(config: Mapping[str, Any]) -> RetryPolicy:
    """Extract the optional retry policy from a raw configuration.

    A configuration without ``testing.retry`` keeps the Phase 3 default of one
    attempt per slot, so existing configuration files stay valid.
    """
    testing = config.get("testing")
    if not isinstance(testing, Mapping):
        return RetryPolicy()
    retry = testing.get("retry")
    if retry is None:
        return RetryPolicy()
    if not isinstance(retry, Mapping):
        raise SamplingConfigurationError(
            "Configuration 'testing.retry' must be a mapping"
        )

    return resolve_retry_policy(
        retry.get("max_attempts"),
        retry.get("retry_delay_seconds"),
    )
