from dataclasses import dataclass


@dataclass(frozen=True)
class AmmeterSettings:
    """Connection details for one configured ammeter."""

    name: str
    port: int
    command: bytes
