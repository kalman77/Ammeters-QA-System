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
- `src/domain/models/`: immutable settings, one dataclass per module
- `src/application/ports/`: dependency contracts used by application logic
- `src/application/use_cases/`: framework-independent workflows
- `src/infrastructure/config/`: YAML loading and configuration resolution
- `src/infrastructure/emulators/`: registry and lifecycle adapters, one
  operation per module
- `src/bootstrap/`: dependency composition
- `src/presentation/console/`: console output formatting
- `Ammeters/`: existing emulator and socket infrastructure adapters
- `config/config.yaml`: runtime and future test-framework configuration
- `src/testing/`: Phase 2 test-framework implementation area
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
  example's `run_test` call signature. Sampling remains Phase 2 work.
- Refactored the Phase 1 implementation into domain, application,
  infrastructure, bootstrap, and presentation layers. `main.py` now delegates
  to the bootstrap layer instead of owning configuration and thread lifecycle.

## Run Phase 1 tests

```sh
python -m unittest discover -s tests -v
```
