from dataclasses import dataclass
from typing import Tuple

from src.domain.models.ammeter_settings import AmmeterSettings
from src.domain.models.network_settings import NetworkSettings


@dataclass(frozen=True)
class RuntimeSettings:
    """Validated settings required to execute an ammeter run."""

    network: NetworkSettings
    ammeters: Tuple[AmmeterSettings, ...]
