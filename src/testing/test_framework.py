from functools import partial
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, Type, Union

from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.application.errors.framework_configuration_error import (
    FrameworkConfigurationError,
)
from src.application.ports.ammeter_client import AmmeterClient
from src.application.ports.emulator_starter import EmulatorStarter
from src.application.ports.emulator_stopper import EmulatorStopper
from src.application.ports.monotonic_clock import MonotonicClock
from src.application.ports.sleeper import Sleeper
from src.application.ports.utc_clock import UtcClock
from src.application.use_cases.analyze_sampling_result import (
    analyze_sampling_result,
)
from src.application.use_cases.run_ammeter_sampling_test import (
    run_ammeter_sampling_test,
)
from src.application.use_cases.run_single_ammeter_test import (
    run_single_ammeter_test,
)
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings
from src.infrastructure.clients.read_ammeter_current import (
    read_ammeter_current,
)
from src.infrastructure.config.default_config_path import DEFAULT_CONFIG_PATH
from src.infrastructure.config.load_yaml_config import load_yaml_config
from src.infrastructure.config.resolve_runtime_settings import (
    resolve_runtime_settings,
)
from src.infrastructure.emulators.emulator_registry import EMULATOR_REGISTRY
from src.infrastructure.emulators.start_emulators import (
    start_emulators as start_emulators_adapter,
)
from src.infrastructure.emulators.stop_emulators import (
    stop_emulators as stop_emulators_adapter,
)
from src.infrastructure.time.read_monotonic_time import read_monotonic_time
from src.infrastructure.time.read_utc_time import read_utc_time
from src.infrastructure.time.sleep_for_seconds import sleep_for_seconds
from src.presentation.serialization.measurement_result_to_dict import (
    measurement_result_to_dict,
)
from src.presentation.serialization.sampling_analysis_to_dict import (
    sampling_analysis_to_dict,
)
from src.presentation.serialization.sampling_result_to_dict import (
    sampling_result_to_dict,
)
from src.testing.resolve_framework_sampling_settings import (
    resolve_framework_sampling_settings,
)


class AmmeterTestFramework:
    """Public unified API for configured ammeter measurements."""

    def __init__(
        self,
        config_path: Union[str, Path] = DEFAULT_CONFIG_PATH,
        *,
        emulator_registry: Optional[
            Mapping[str, Type[AmmeterEmulatorBase]]
        ] = None,
        start_emulators: Optional[EmulatorStarter] = None,
        stop_emulators: Optional[EmulatorStopper] = None,
        request_current: Optional[AmmeterClient] = None,
        monotonic_clock: Optional[MonotonicClock] = None,
        utc_clock: Optional[UtcClock] = None,
        sleeper: Optional[Sleeper] = None,
    ):
        registry = (
            EMULATOR_REGISTRY
            if emulator_registry is None
            else emulator_registry
        )
        try:
            self.config = load_yaml_config(config_path)
            self._runtime_settings = resolve_runtime_settings(
                self.config,
                registry.keys(),
            )
        except (OSError, ValueError) as exc:
            raise FrameworkConfigurationError(
                f"Unable to initialize the ammeter framework: {exc}"
            ) from exc

        self._start_emulators = start_emulators or partial(
            start_emulators_adapter,
            emulator_registry=registry,
        )
        self._stop_emulators = (
            stop_emulators or stop_emulators_adapter
        )
        self._request_current = request_current or read_ammeter_current
        self._monotonic_clock = monotonic_clock or read_monotonic_time
        self._utc_clock = utc_clock or read_utc_time
        self._sleeper = sleeper or sleep_for_seconds

    @property
    def ammeter_types(self) -> Tuple[str, ...]:
        """Return configured ammeter types in execution order."""
        return tuple(
            settings.name for settings in self._runtime_settings.ammeters
        )

    def measure(self, ammeter_type: object) -> MeasurementResult:
        """Execute the canonical typed measurement API."""
        return run_single_ammeter_test(
            self._runtime_settings,
            ammeter_type,
            start_emulators=self._start_emulators,
            stop_emulators=self._stop_emulators,
            request_current=self._request_current,
            monotonic_clock=self._monotonic_clock,
            utc_clock=self._utc_clock,
        )

    def run_test(self, ammeter_type: object) -> Dict[str, Any]:
        """Compatibility API returning a JSON-friendly result dictionary."""
        return measurement_result_to_dict(self.measure(ammeter_type))

    def measure_all(self) -> Dict[str, MeasurementResult]:
        """Measure every configured ammeter using the typed API."""
        return {
            ammeter_type: self.measure(ammeter_type)
            for ammeter_type in self.ammeter_types
        }

    def run_all_tests(self) -> Dict[str, Dict[str, Any]]:
        """Measure every configured ammeter using serialized results."""
        return {
            ammeter_type: measurement_result_to_dict(result)
            for ammeter_type, result in self.measure_all().items()
        }

    @property
    def sampling_settings(self) -> SamplingSettings:
        """Resolve the configured Phase 3 sampling window lazily."""
        return resolve_framework_sampling_settings(
            self.config,
            None,
            None,
            None,
        )

    def _sample_with_settings(
        self,
        ammeter_type: object,
        sampling_settings: SamplingSettings,
    ) -> SamplingResult:
        return run_ammeter_sampling_test(
            self._runtime_settings,
            sampling_settings,
            ammeter_type,
            start_emulators=self._start_emulators,
            stop_emulators=self._stop_emulators,
            request_current=self._request_current,
            monotonic_clock=self._monotonic_clock,
            utc_clock=self._utc_clock,
            sleeper=self._sleeper,
        )

    def sample(
        self,
        ammeter_type: object,
        *,
        measurements_count: Optional[object] = None,
        total_duration_seconds: Optional[object] = None,
        sampling_frequency_hz: Optional[object] = None,
    ) -> SamplingResult:
        """Run the canonical typed sampling API for one ammeter."""
        sampling_settings = resolve_framework_sampling_settings(
            self.config,
            measurements_count,
            total_duration_seconds,
            sampling_frequency_hz,
        )
        return self._sample_with_settings(
            ammeter_type,
            sampling_settings,
        )

    def sample_all(
        self,
        *,
        measurements_count: Optional[object] = None,
        total_duration_seconds: Optional[object] = None,
        sampling_frequency_hz: Optional[object] = None,
    ) -> Dict[str, SamplingResult]:
        """Sample every configured ammeter with one resolved schedule."""
        sampling_settings = resolve_framework_sampling_settings(
            self.config,
            measurements_count,
            total_duration_seconds,
            sampling_frequency_hz,
        )
        return {
            ammeter_type: self._sample_with_settings(
                ammeter_type,
                sampling_settings,
            )
            for ammeter_type in self.ammeter_types
        }

    def run_sampling_test(
        self,
        ammeter_type: object,
        *,
        measurements_count: Optional[object] = None,
        total_duration_seconds: Optional[object] = None,
        sampling_frequency_hz: Optional[object] = None,
    ) -> Dict[str, Any]:
        """Run one sampling window and return a JSON-friendly dictionary."""
        result = self.sample(
            ammeter_type,
            measurements_count=measurements_count,
            total_duration_seconds=total_duration_seconds,
            sampling_frequency_hz=sampling_frequency_hz,
        )
        return sampling_result_to_dict(result)

    def run_all_sampling_tests(
        self,
        *,
        measurements_count: Optional[object] = None,
        total_duration_seconds: Optional[object] = None,
        sampling_frequency_hz: Optional[object] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Run and serialize one sampling window for every ammeter."""
        results = self.sample_all(
            measurements_count=measurements_count,
            total_duration_seconds=total_duration_seconds,
            sampling_frequency_hz=sampling_frequency_hz,
        )
        return {
            ammeter_type: sampling_result_to_dict(result)
            for ammeter_type, result in results.items()
        }

    def analyze(
        self,
        ammeter_type: object,
        *,
        measurements_count: Optional[object] = None,
        total_duration_seconds: Optional[object] = None,
        sampling_frequency_hz: Optional[object] = None,
    ) -> SamplingAnalysis:
        """Sample one ammeter once and return its statistical analysis."""
        sampling_result = self.sample(
            ammeter_type,
            measurements_count=measurements_count,
            total_duration_seconds=total_duration_seconds,
            sampling_frequency_hz=sampling_frequency_hz,
        )
        return analyze_sampling_result(sampling_result)

    def analyze_all(
        self,
        *,
        measurements_count: Optional[object] = None,
        total_duration_seconds: Optional[object] = None,
        sampling_frequency_hz: Optional[object] = None,
    ) -> Dict[str, SamplingAnalysis]:
        """Sample and statistically analyze every configured ammeter."""
        sampling_results = self.sample_all(
            measurements_count=measurements_count,
            total_duration_seconds=total_duration_seconds,
            sampling_frequency_hz=sampling_frequency_hz,
        )
        return {
            ammeter_type: analyze_sampling_result(result)
            for ammeter_type, result in sampling_results.items()
        }

    def run_analysis(
        self,
        ammeter_type: object,
        *,
        measurements_count: Optional[object] = None,
        total_duration_seconds: Optional[object] = None,
        sampling_frequency_hz: Optional[object] = None,
    ) -> Dict[str, Any]:
        """Sample, analyze, and serialize one configured ammeter."""
        analysis = self.analyze(
            ammeter_type,
            measurements_count=measurements_count,
            total_duration_seconds=total_duration_seconds,
            sampling_frequency_hz=sampling_frequency_hz,
        )
        return sampling_analysis_to_dict(analysis)

    def run_all_analyses(
        self,
        *,
        measurements_count: Optional[object] = None,
        total_duration_seconds: Optional[object] = None,
        sampling_frequency_hz: Optional[object] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Sample, analyze, and serialize every configured ammeter."""
        analyses = self.analyze_all(
            measurements_count=measurements_count,
            total_duration_seconds=total_duration_seconds,
            sampling_frequency_hz=sampling_frequency_hz,
        )
        return {
            ammeter_type: sampling_analysis_to_dict(analysis)
            for ammeter_type, analysis in analyses.items()
        }
