import ast
import importlib
import io
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

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
            "src/domain/models/network_settings.py": "NetworkSettings",
            "src/domain/models/runtime_settings.py": "RuntimeSettings",
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
                "src/infrastructure/config/load_yaml_config.py"
            ): "load_yaml_config",
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
                "src/application/use_cases/run_ammeter_smoke_test.py"
            ): "run_ammeter_smoke_test",
            (
                "src/presentation/console/format_measurements_table.py"
            ): "format_measurements_table",
            (
                "src/presentation/console/print_measurements.py"
            ): "print_measurements",
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
                    if module == "Ammeters"
                    or module.startswith("Ammeters.")
                    or module == "src.infrastructure"
                    or module.startswith("src.infrastructure.")
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
