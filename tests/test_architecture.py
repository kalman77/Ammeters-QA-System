import ast
import importlib
import io
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CleanArchitectureTests(unittest.TestCase):
    def _tree(self, relative_path: str) -> ast.Module:
        path = PROJECT_ROOT / relative_path
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def _imported_modules(self, tree: ast.Module) -> set[str]:
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        return modules

    def test_main_is_a_thin_public_entry_point(self) -> None:
        tree = self._tree("main.py")
        functions = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        classes = [
            node.name for node in tree.body if isinstance(node, ast.ClassDef)
        ]
        imports = self._imported_modules(tree)

        self.assertEqual(functions, ["main"])
        self.assertEqual(classes, [])
        self.assertTrue(
            {
                "dataclasses",
                "threading",
                "time",
                "socket",
                "yaml",
                "Ammeters.client",
                "Ammeters.Greenlee_Ammeter",
                "Ammeters.Entes_Ammeter",
                "Ammeters.Circutor_Ammeter",
                "src.infrastructure.config.default_config_path",
            }.isdisjoint(imports)
        )

    def test_each_dataclass_has_a_dedicated_module(self) -> None:
        modules = {
            "src/domain/models/ammeter_settings.py": "AmmeterSettings",
            (
                "src/domain/models/archived_run_query.py"
            ): "ArchivedRunQuery",
            (
                "src/domain/models/archived_test_run.py"
            ): "ArchivedTestRun",
            (
                "src/domain/models/current_statistics.py"
            ): "CurrentStatistics",
            (
                "src/domain/models/current_statistics_delta.py"
            ): "CurrentStatisticsDelta",
            (
                "src/domain/models/historical_comparison.py"
            ): "HistoricalComparison",
            "src/domain/models/measurement.py": "Measurement",
            "src/domain/models/measurement_error.py": "MeasurementError",
            (
                "src/domain/models/measurement_result.py"
            ): "MeasurementResult",
            "src/domain/models/network_settings.py": "NetworkSettings",
            (
                "src/domain/models/run_metadata_entry.py"
            ): "RunMetadataEntry",
            "src/domain/models/runtime_settings.py": "RuntimeSettings",
            "src/domain/models/sample_result.py": "SampleResult",
            (
                "src/domain/models/sampling_analysis.py"
            ): "SamplingAnalysis",
            "src/domain/models/sampling_result.py": "SamplingResult",
            "src/domain/models/sampling_settings.py": "SamplingSettings",
            (
                "src/infrastructure/emulators/running_emulator.py"
            ): "RunningEmulator",
        }

        for relative_path, expected_class in modules.items():
            with self.subTest(module=relative_path):
                tree = self._tree(relative_path)
                classes = [
                    node.name
                    for node in tree.body
                    if isinstance(node, ast.ClassDef)
                ]
                functions = [
                    node.name
                    for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                self.assertEqual(classes, [expected_class])
                self.assertEqual(functions, [])

    def test_each_extracted_operation_has_a_dedicated_module(self) -> None:
        modules = {
            (
                "src/application/use_cases/"
                "archive_sampling_analyses.py"
            ): "archive_sampling_analyses",
            (
                "src/application/use_cases/"
                "archive_sampling_analysis.py"
            ): "archive_sampling_analysis",
            (
                "src/infrastructure/config/load_yaml_config.py"
            ): "load_yaml_config",
            (
                "src/infrastructure/config/"
                "read_result_archive_directory.py"
            ): "read_result_archive_directory",
            (
                "src/infrastructure/config/resolve_positive_number.py"
            ): "resolve_positive_number",
            (
                "src/infrastructure/config/resolve_runtime_settings.py"
            ): "resolve_runtime_settings",
            (
                "src/infrastructure/emulators/serve_emulator.py"
            ): "serve_emulator",
            (
                "src/infrastructure/emulators/start_emulators.py"
            ): "start_emulators",
            (
                "src/infrastructure/emulators/join_emulator_threads.py"
            ): "join_emulator_threads",
            (
                "src/infrastructure/emulators/stop_emulators.py"
            ): "stop_emulators",
            (
                "src/application/use_cases/analyze_sampling_result.py"
            ): "analyze_sampling_result",
            (
                "src/application/use_cases/"
                "compare_archived_test_runs.py"
            ): "compare_archived_test_runs",
            (
                "src/domain/services/"
                "calculate_current_statistics.py"
            ): "calculate_current_statistics",
            (
                "src/domain/services/"
                "calculate_current_statistics_delta.py"
            ): "calculate_current_statistics_delta",
            (
                "src/application/use_cases/"
                "find_archived_test_runs.py"
            ): "find_archived_test_runs",
            (
                "src/application/use_cases/run_ammeter_smoke_test.py"
            ): "run_ammeter_smoke_test",
            (
                "src/application/use_cases/measure_running_ammeter.py"
            ): "measure_running_ammeter",
            (
                "src/application/use_cases/normalize_ammeter_type.py"
            ): "normalize_ammeter_type",
            (
                "src/application/use_cases/run_single_ammeter_test.py"
            ): "run_single_ammeter_test",
            (
                "src/application/use_cases/select_ammeter_settings.py"
            ): "select_ammeter_settings",
            (
                "src/application/use_cases/validate_current.py"
            ): "validate_current",
            (
                "src/application/use_cases/collect_scheduled_sample.py"
            ): "collect_scheduled_sample",
            (
                "src/application/use_cases/resolve_sampling_settings.py"
            ): "resolve_sampling_settings",
            (
                "src/application/use_cases/"
                "resolve_archived_run_query.py"
            ): "resolve_archived_run_query",
            (
                "src/application/use_cases/resolve_run_metadata.py"
            ): "resolve_run_metadata",
            (
                "src/application/use_cases/"
                "retrieve_archived_test_run.py"
            ): "retrieve_archived_test_run",
            (
                "src/application/use_cases/run_ammeter_sampling_test.py"
            ): "run_ammeter_sampling_test",
            (
                "src/application/use_cases/wait_until_deadline.py"
            ): "wait_until_deadline",
            (
                "src/infrastructure/clients/read_ammeter_current.py"
            ): "read_ammeter_current",
            (
                "src/infrastructure/identifiers/generate_run_id.py"
            ): "generate_run_id",
            (
                "src/infrastructure/persistence/"
                "analysis_documents_match.py"
            ): "analysis_documents_match",
            (
                "src/infrastructure/persistence/"
                "archive_documents_match.py"
            ): "archive_documents_match",
            (
                "src/infrastructure/persistence/"
                "archived_test_run_from_dict.py"
            ): "archived_test_run_from_dict",
            (
                "src/infrastructure/persistence/"
                "archived_test_run_to_archive_dict.py"
            ): "archived_test_run_to_archive_dict",
            (
                "src/infrastructure/persistence/"
                "json_values_are_identical.py"
            ): "json_values_are_identical",
            (
                "src/infrastructure/persistence/"
                "list_archived_test_runs.py"
            ): "list_archived_test_runs",
            (
                "src/infrastructure/persistence/"
                "load_archived_test_run.py"
            ): "load_archived_test_run",
            (
                "src/infrastructure/persistence/"
                "measurement_error_from_dict.py"
            ): "measurement_error_from_dict",
            (
                "src/infrastructure/persistence/"
                "measurement_result_from_dict.py"
            ): "measurement_result_from_dict",
            (
                "src/infrastructure/persistence/"
                "measurement_result_to_archive_dict.py"
            ): "measurement_result_to_archive_dict",
            (
                "src/infrastructure/persistence/"
                "parse_utc_timestamp.py"
            ): "parse_utc_timestamp",
            (
                "src/infrastructure/persistence/"
                "publish_archive_without_overwrite.py"
            ): "publish_archive_without_overwrite",
            (
                "src/infrastructure/persistence/"
                "reject_duplicate_json_object_keys.py"
            ): "reject_duplicate_json_object_keys",
            (
                "src/infrastructure/persistence/"
                "reject_non_finite_json_constant.py"
            ): "reject_non_finite_json_constant",
            (
                "src/infrastructure/persistence/"
                "sample_result_from_dict.py"
            ): "sample_result_from_dict",
            (
                "src/infrastructure/persistence/"
                "sampling_analysis_from_dict.py"
            ): "sampling_analysis_from_dict",
            (
                "src/infrastructure/persistence/"
                "sampling_analysis_to_archive_dict.py"
            ): "sampling_analysis_to_archive_dict",
            (
                "src/infrastructure/persistence/"
                "sampling_result_from_dict.py"
            ): "sampling_result_from_dict",
            (
                "src/infrastructure/persistence/"
                "sampling_result_to_archive_dict.py"
            ): "sampling_result_to_archive_dict",
            (
                "src/infrastructure/persistence/"
                "save_archived_test_run.py"
            ): "save_archived_test_run",
            (
                "src/infrastructure/config/read_sampling_settings.py"
            ): "read_sampling_settings",
            (
                "src/infrastructure/time/read_monotonic_time.py"
            ): "read_monotonic_time",
            (
                "src/infrastructure/time/read_utc_time.py"
            ): "read_utc_time",
            (
                "src/infrastructure/time/sleep_for_seconds.py"
            ): "sleep_for_seconds",
            (
                "src/presentation/console/"
                "format_analysis_results_table.py"
            ): "format_analysis_results_table",
            (
                "src/presentation/console/"
                "format_archived_test_runs_table.py"
            ): "format_archived_test_runs_table",
            (
                "src/presentation/console/"
                "format_historical_comparison_table.py"
            ): "format_historical_comparison_table",
            (
                "src/presentation/console/format_measurements_table.py"
            ): "format_measurements_table",
            (
                "src/presentation/console/"
                "format_measurement_results_table.py"
            ): "format_measurement_results_table",
            (
                "src/presentation/console/print_analysis_results.py"
            ): "print_analysis_results",
            (
                "src/presentation/console/"
                "print_archived_test_runs.py"
            ): "print_archived_test_runs",
            (
                "src/presentation/console/"
                "print_historical_comparison.py"
            ): "print_historical_comparison",
            (
                "src/presentation/console/print_measurements.py"
            ): "print_measurements",
            (
                "src/presentation/console/print_measurement_results.py"
            ): "print_measurement_results",
            (
                "src/presentation/console/format_sampling_results_table.py"
            ): "format_sampling_results_table",
            (
                "src/presentation/console/print_sampling_results.py"
            ): "print_sampling_results",
            (
                "src/presentation/serialization/"
                "archived_test_run_to_dict.py"
            ): "archived_test_run_to_dict",
            (
                "src/presentation/serialization/"
                "historical_comparison_to_dict.py"
            ): "historical_comparison_to_dict",
            (
                "src/presentation/serialization/"
                "measurement_result_to_dict.py"
            ): "measurement_result_to_dict",
            (
                "src/presentation/serialization/"
                "sampling_analysis_to_dict.py"
            ): "sampling_analysis_to_dict",
            (
                "src/presentation/serialization/"
                "sampling_result_to_dict.py"
            ): "sampling_result_to_dict",
            (
                "src/testing/resolve_framework_sampling_settings.py"
            ): "resolve_framework_sampling_settings",
            (
                "src/testing/build_ammeter_result_manager.py"
            ): "build_ammeter_result_manager",
            (
                "src/domain/services/normalize_run_id.py"
            ): "normalize_run_id",
            "src/bootstrap/run_application.py": "run_application",
        }

        for relative_path, expected_function in modules.items():
            with self.subTest(module=relative_path):
                tree = self._tree(relative_path)
                functions = [
                    node.name
                    for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                self.assertEqual(functions, [expected_function])

    def test_application_layer_does_not_import_infrastructure(self) -> None:
        application_root = PROJECT_ROOT / "src" / "application"
        for path in application_root.rglob("*.py"):
            with self.subTest(module=path.relative_to(PROJECT_ROOT)):
                imports = self._imported_modules(
                    ast.parse(
                        path.read_text(encoding="utf-8"),
                        filename=str(path),
                    )
                )
                forbidden = [
                    module
                    for module in imports
                    if module in {"socket", "time", "yaml", "Ammeters"}
                    or module.startswith("Ammeters.")
                    or (
                        module.startswith("src.")
                        and module != "src.application"
                        and not module.startswith("src.application.")
                        and module != "src.domain"
                        and not module.startswith("src.domain.")
                    )
                ]
                self.assertEqual(forbidden, [])

    def test_phase5_inner_layers_do_not_import_storage_adapters(
        self,
    ) -> None:
        phase5_inner_modules = (
            "src/domain/models/archived_run_query.py",
            "src/domain/models/archived_test_run.py",
            "src/domain/models/current_statistics_delta.py",
            "src/domain/models/historical_comparison.py",
            "src/domain/models/run_metadata_entry.py",
            (
                "src/domain/services/"
                "calculate_current_statistics_delta.py"
            ),
            "src/domain/services/normalize_run_id.py",
            (
                "src/application/use_cases/"
                "archive_sampling_analyses.py"
            ),
            (
                "src/application/use_cases/"
                "archive_sampling_analysis.py"
            ),
            (
                "src/application/use_cases/"
                "compare_archived_test_runs.py"
            ),
            (
                "src/application/use_cases/"
                "find_archived_test_runs.py"
            ),
            (
                "src/application/use_cases/"
                "resolve_archived_run_query.py"
            ),
            (
                "src/application/use_cases/resolve_run_metadata.py"
            ),
            (
                "src/application/use_cases/"
                "retrieve_archived_test_run.py"
            ),
        )
        forbidden_prefixes = (
            "src.infrastructure.config",
            "src.infrastructure.identifiers",
            "src.infrastructure.persistence",
        )
        forbidden_storage_modules = {
            "json",
            "os",
            "pathlib",
            "tempfile",
            "yaml",
        }

        for relative_path in phase5_inner_modules:
            with self.subTest(module=relative_path):
                imports = self._imported_modules(
                    self._tree(relative_path)
                )
                forbidden = [
                    module
                    for module in imports
                    if module in forbidden_storage_modules
                    or module.startswith(forbidden_prefixes)
                ]
                self.assertEqual(forbidden, [])

    def test_phase5_ports_and_result_manager_are_separated(self) -> None:
        modules = {
            (
                "src/application/ports/archived_run_lister.py"
            ): "ArchivedRunLister",
            (
                "src/application/ports/archived_run_loader.py"
            ): "ArchivedRunLoader",
            (
                "src/application/ports/archived_run_saver.py"
            ): "ArchivedRunSaver",
            (
                "src/application/ports/run_id_generator.py"
            ): "RunIdGenerator",
            (
                "src/testing/ammeter_result_manager.py"
            ): "AmmeterResultManager",
        }

        for relative_path, expected_class in modules.items():
            with self.subTest(module=relative_path):
                tree = self._tree(relative_path)
                classes = [
                    node.name
                    for node in tree.body
                    if isinstance(node, ast.ClassDef)
                ]
                functions = [
                    node.name
                    for node in tree.body
                    if isinstance(
                        node,
                        (ast.FunctionDef, ast.AsyncFunctionDef),
                    )
                ]
                self.assertEqual(classes, [expected_class])
                self.assertEqual(functions, [])

    def test_framework_archive_storage_is_lazy_when_unused(self) -> None:
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            config_path = temporary_root / "config.yaml"
            archive_path = temporary_root / "unused-archive"
            config_path.write_text(
                """
testing:
  sampling:
    measurements_count: 2
    total_duration_seconds: 1.0
    sampling_frequency_hz: 2.0
network:
  host: "127.0.0.1"
  connect_timeout_seconds: 1.0
  read_timeout_seconds: 1.0
  startup_timeout_seconds: 1.0
  shutdown_timeout_seconds: 1.0
ammeters:
  greenlee:
    port: 0
    command: "GREENLEE"
  entes:
    port: 0
    command: "ENTES"
  circutor:
    port: 0
    command: "CIRCUTOR"
result_management:
  archive_directory: "unused-archive"
""".strip(),
                encoding="utf-8",
            )

            self.assertFalse(archive_path.exists())
            output = io.StringIO()
            with redirect_stdout(output):
                framework_module = importlib.import_module(
                    "src.testing.test_framework"
                )
                framework_module = importlib.reload(framework_module)
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(archive_path.exists())

            framework = framework_module.AmmeterTestFramework(
                config_path
            )

            self.assertEqual(
                framework.ammeter_types,
                ("greenlee", "entes", "circutor"),
            )
            self.assertEqual(
                framework.sampling_settings.measurements_count,
                2,
            )
            self.assertFalse(archive_path.exists())

    def test_domain_layer_does_not_import_outer_layers(self) -> None:
        domain_root = PROJECT_ROOT / "src" / "domain"
        for path in domain_root.rglob("*.py"):
            with self.subTest(module=path.relative_to(PROJECT_ROOT)):
                imports = self._imported_modules(
                    ast.parse(
                        path.read_text(encoding="utf-8"),
                        filename=str(path),
                    )
                )
                forbidden = [
                    module
                    for module in imports
                    if module in {"yaml", "Ammeters"}
                    or module.startswith("Ammeters.")
                    or (
                        module.startswith("src.")
                        and module != "src.domain"
                        and not module.startswith("src.domain.")
                    )
                ]
                self.assertEqual(forbidden, [])

    def test_importing_main_has_no_runtime_side_effects(self) -> None:
        baseline_threads = {id(thread) for thread in threading.enumerate()}
        output = io.StringIO()

        with redirect_stdout(output):
            importlib.reload(main)

        new_threads = [
            thread
            for thread in threading.enumerate()
            if id(thread) not in baseline_threads
        ]
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(new_threads, [])
