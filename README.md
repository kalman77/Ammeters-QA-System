# Ammeter Emulators

This project provides localhost emulators for Greenlee, ENTES, and CIRCUTOR
ammeters. Each emulator runs in its own thread and returns a simulated current
measurement through a small TCP protocol.

Commands and responses are newline-framed on the wire so TCP fragmentation
cannot produce partial measurements. The server also accepts the original exact
command bytes without a newline for compatibility with existing callers.

## Requirements

- Python 3.9 or newer
- PyYAML 6.0 or newer

Create a project-local environment and install the runtime dependency:

```sh
python -m venv .venv
```

Linux/macOS:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Phase 1 was verified with Python 3.14.6 and PyYAML 6.0.3. No other external
libraries are required or were installed.

## Run the emulator smoke test

From the project directory:

```sh
python main.py
```

`main.py` reads the host, ports, commands, and timeouts from
`config/config.yaml`. It starts all three servers, waits until their listening
sockets are ready, requests one current measurement from each, prints the
results, and stops every server thread.

Results are displayed in an aligned console table:

```text
Ammeter Measurement Results
+----------+-----------+------+
| Ammeter  |   Current | Unit |
+----------+-----------+------+
| GREENLEE |  0.420000 | A    |
| ENTES    | 72.500000 | A    |
| CIRCUTOR |  0.030000 | A    |
+----------+-----------+------+
```

The callable `main.main()` also returns the measurements as:

```python
{
    "greenlee": 0.42,
    "entes": 72.5,
    "circutor": 0.03,
}
```

Values change on every run because the emulator inputs are random.

## Unified test framework (Phase 2)

`AmmeterTestFramework` is the public API for measuring one configured ammeter.
The canonical `measure()` method returns an immutable `MeasurementResult`:

```python
from src.testing.test_framework import AmmeterTestFramework

framework = AmmeterTestFramework()
result = framework.measure("greenlee")

print(result.ammeter_type)             # greenlee
print(result.status.value)             # success, failed, or partial
print(result.current, result.unit)     # for example: 0.42 A
print(result.request_latency_seconds)
print(result.errors)
```

Ammeter names are stripped and matched case-insensitively. The supported names
are available through `framework.ammeter_types`. Use `measure_all()` to receive
a `dict[str, MeasurementResult]` in configured execution order.

`run_test()` preserves a dictionary-oriented API. It executes the same typed
measurement and serializes the result into JSON-friendly values:

```python
result = framework.run_test("greenlee")
```

```python
{
    "ammeter_type": "greenlee",
    "status": "success",
    "timestamp_utc": "2026-08-01T09:30:00Z",
    "elapsed_seconds": 0.012,
    "current": 0.42,
    "unit": "A",
    "request_latency_seconds": 0.004,
    "errors": [],
}
```

`run_all_tests()` returns the same serialized shape for every configured
ammeter.

### Status and error semantics

| Status | Measurement fields | Errors |
|---|---|---|
| `success` | `current` and request latency are present | Empty |
| `failed` | `current` and request latency are `None` | One or more operational errors |
| `partial` | A valid measurement is present | A later shutdown error is recorded |

Operational failures are returned in `errors` with stable codes:
`emulator_start_failed`, `measurement_request_failed`,
`invalid_measurement`, and `emulator_stop_failed`. Invalid selectors and
configuration are caller errors rather than measurement outcomes:

- `FrameworkConfigurationError` means the YAML could not be loaded or resolved.
- `InvalidAmmeterTypeError` means the selector was not a non-empty string.
- `UnsupportedAmmeterError` means the normalized name is not configured.

### Run the example

From the project root, invoke the example as a module so project imports resolve
consistently:

```sh
python -m examples.run_tests
```

The example calls `measure_all()` and prints the typed results, including status,
latency, and structured error details.

### Sampling scope

Phase 2 performs exactly one measurement request for each selected ammeter.
The `testing.sampling` placeholders in `config/config.yaml` are intentionally
not consumed yet. Measurement count, total duration, sampling frequency, and
precise sampling schedules are deferred explicitly to Phase 3.

## Configured protocols

`config/config.yaml` is the runtime source of truth.

| Ammeter | Default port | Command |
|---|---:|---|
| Greenlee | 5000 | `MEASURE_GREENLEE -get_measurement` |
| ENTES | 5001 | `MEASURE_ENTES -get_data` |
| CIRCUTOR | 5002 | `MEASURE_CIRCUTOR -get_measurement -current` |

The same configuration file defines connection, read, startup, and shutdown
timeouts. Port `0` may be used in test configurations to let the operating
system choose a free port.

## Project structure

- `main.py`: thin public entry point and CLI exception boundary
- `src/domain/models/`: immutable settings and typed measurement results, one
  dataclass per module
- `src/application/ports/`: dependency contracts used by application logic
- `src/application/use_cases/`: selection, validation, and measurement workflows
- `src/application/errors/`: typed selector, configuration, and operational
  errors
- `src/infrastructure/config/`: YAML loading and configuration resolution
- `src/infrastructure/emulators/`: registry and lifecycle adapters, one
  operation per module
- `src/infrastructure/clients/`: measurement transport adapters
- `src/infrastructure/time/`: UTC and monotonic clock adapters
- `src/bootstrap/`: dependency composition
- `src/presentation/console/`: smoke-test and typed-result table formatting
- `src/presentation/serialization/`: JSON-friendly result serialization
- `Ammeters/`: existing emulator and socket infrastructure adapters
- `config/config.yaml`: runtime and future test-framework configuration
- `src/testing/`: public `AmmeterTestFramework` facade
- `examples/`: framework usage examples
- `tests/`: behavioral and architecture regression tests

See [Architecture](docs/architecture.md) for dependency direction and design
decisions.

## Phase 1 fixes

- Activated the previously empty ammeter configuration.
- Aligned the runtime ports with the documented `5000`, `5001`, and `5002`
  assignments.
- Corrected the documented CIRCUTOR command to include the emulator's required
  `-current` suffix.
- Changed the client to return a validated finite `float` instead of only
  printing socket data.
- Added bounded connection/read timeouts and clear invalid-response errors.
- Added complete-frame reads so fragmented TCP commands or values cannot be
  mistaken for complete messages.
- Replaced the fixed startup delay with a listener-readiness signal.
- Added cooperative server shutdown, bounded thread joins, ephemeral-port
  support, and socket-address reuse for reliable repeated runs.
- Corrected the incomplete framework module's missing type import and the
  example's original `run_test` call signature.
- Refactored the Phase 1 implementation into domain, application,
  infrastructure, bootstrap, and presentation layers. `main.py` now delegates
  to the bootstrap layer instead of owning configuration and thread lifecycle.

## Phase 2 additions

- Added a unified, typed single-ammeter measurement API.
- Added immutable measurements, result envelopes, statuses, and structured
  error details.
- Added JSON-friendly `run_test()` and `run_all_tests()` compatibility APIs.
- Added validated selector handling, UTC timestamps, elapsed time, and request
  latency.
- Added typed-result console presentation and a runnable module example.
- Kept sampling mechanics deferred to Phase 3.

## Run tests

```sh
python -m unittest discover -s tests -v
```
