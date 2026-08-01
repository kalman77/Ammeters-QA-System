from functools import partial
from pathlib import Path
from typing import Dict, Union

from Ammeters.client import request_current_from_ammeter
from src.application.use_cases.run_ammeter_smoke_test import (
    run_ammeter_smoke_test,
)
from src.infrastructure.config.default_config_path import DEFAULT_CONFIG_PATH
from src.infrastructure.config.load_yaml_config import load_yaml_config
from src.infrastructure.config.resolve_runtime_settings import (
    resolve_runtime_settings,
)
from src.infrastructure.emulators.emulator_registry import EMULATOR_REGISTRY
from src.infrastructure.emulators.start_emulators import start_emulators
from src.infrastructure.emulators.stop_emulators import stop_emulators
from src.presentation.console.print_measurements import print_measurements


def run_application(
    config_path: Union[str, Path] = DEFAULT_CONFIG_PATH,
    *,
    emit: bool = True,
) -> Dict[str, float]:
    """Compose dependencies and execute the ammeter smoke-test use case."""
    raw_config = load_yaml_config(config_path)
    runtime_settings = resolve_runtime_settings(
        raw_config,
        EMULATOR_REGISTRY.keys(),
    )
    measurements = run_ammeter_smoke_test(
        runtime_settings,
        start_emulators=partial(
            start_emulators,
            emulator_registry=EMULATOR_REGISTRY,
        ),
        stop_emulators=stop_emulators,
        request_current=request_current_from_ammeter,
    )

    if emit:
        print_measurements(measurements)

    return measurements
