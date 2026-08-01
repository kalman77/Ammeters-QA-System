from typing import Any, Iterable, List, Mapping, Set

from src.domain.models.ammeter_settings import AmmeterSettings
from src.domain.models.network_settings import NetworkSettings
from src.domain.models.runtime_settings import RuntimeSettings
from src.infrastructure.config.resolve_positive_number import (
    resolve_positive_number,
)


def resolve_runtime_settings(
    config: Mapping[str, Any],
    supported_ammeter_names: Iterable[str],
) -> RuntimeSettings:
    """Validate raw configuration and return immutable runtime settings."""
    network = config.get("network")
    if not isinstance(network, dict):
        raise ValueError("Configuration must define a 'network' mapping")

    host = network.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("network.host must be a non-empty string")

    network_settings = NetworkSettings(
        host=host.strip(),
        connect_timeout_seconds=resolve_positive_number(
            network, "connect_timeout_seconds"
        ),
        read_timeout_seconds=resolve_positive_number(
            network, "read_timeout_seconds"
        ),
        startup_timeout_seconds=resolve_positive_number(
            network, "startup_timeout_seconds"
        ),
        shutdown_timeout_seconds=resolve_positive_number(
            network, "shutdown_timeout_seconds"
        ),
    )

    ammeters = config.get("ammeters")
    if not isinstance(ammeters, dict):
        raise ValueError("Configuration must define an 'ammeters' mapping")

    settings: List[AmmeterSettings] = []
    configured_ports: Set[int] = set()
    for name in supported_ammeter_names:
        meter = ammeters.get(name)
        if not isinstance(meter, dict):
            raise ValueError(f"Configuration must define ammeters.{name}")

        port = meter.get("port")
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 0 <= port <= 65535
        ):
            raise ValueError(
                f"ammeters.{name}.port must be an integer from 0 to 65535"
            )
        if port != 0 and port in configured_ports:
            raise ValueError(f"ammeters.{name}.port duplicates port {port}")
        configured_ports.add(port)

        command = meter.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(
                f"ammeters.{name}.command must be a non-empty string"
            )
        if "\n" in command or "\r" in command:
            raise ValueError(
                f"ammeters.{name}.command must not contain line delimiters"
            )

        settings.append(
            AmmeterSettings(
                name=name,
                port=port,
                command=command.encode("utf-8"),
            )
        )

    return RuntimeSettings(
        network=network_settings,
        ammeters=tuple(settings),
    )
