import math
from dataclasses import dataclass
from typing import Optional, Union


MetadataValue = Optional[Union[str, bool, int, float]]
MAX_METADATA_KEY_LENGTH = 64
MAX_METADATA_STRING_LENGTH = 1024


@dataclass(frozen=True)
class RunMetadataEntry:
    """One immutable, JSON-safe metadata value attached to an archive."""

    key: str
    value: MetadataValue

    def __post_init__(self) -> None:
        if (
            type(self.key) is not str
            or not self.key.strip()
            or self.key != self.key.strip()
            or len(self.key) > MAX_METADATA_KEY_LENGTH
        ):
            raise ValueError(
                "metadata keys must be trimmed non-empty strings no longer "
                f"than {MAX_METADATA_KEY_LENGTH} characters"
            )
        if self.value is None or type(self.value) is bool:
            return
        if type(self.value) is str:
            if len(self.value) > MAX_METADATA_STRING_LENGTH:
                raise ValueError(
                    "metadata string values cannot exceed "
                    f"{MAX_METADATA_STRING_LENGTH} characters"
                )
            return
        if type(self.value) is int:
            return
        if type(self.value) is float and math.isfinite(self.value):
            return
        raise ValueError(
            "metadata values must be JSON scalars: string, boolean, "
            "integer, finite float, or None"
        )
