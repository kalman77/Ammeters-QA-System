# Architecture

The Phase 1 implementation uses a small Clean Architecture–style separation.
The goal is to keep policies and models independent from socket and YAML
implementations and from console output while avoiding unnecessary framework
code.

## Dependency direction

```text
main.py
  -> bootstrap
       -> application use case
       -> infrastructure adapters
       -> presentation adapter

application
  -> domain models
  -> application ports

infrastructure
  -> domain models
  -> existing Ammeters adapters

domain
  -> Python standard library only
```

The application layer imports neither `Ammeters` nor `src.infrastructure`.
Instead, the bootstrap layer injects the emulator starter, emulator stopper,
and measurement client through application port protocols.

## Responsibilities

| Layer | Responsibility |
|---|---|
| Domain | Immutable validated runtime data |
| Application | Execute the measurement use case through abstract ports |
| Infrastructure/config | Load YAML and resolve it into domain models |
| Infrastructure/emulators | Register, start, monitor, join, and stop emulators |
| Bootstrap | Select concrete adapters and compose dependencies |
| Presentation | Format successful measurements for the console |
| `main.py` | Preserve the public entry point and CLI error boundary |

## File granularity

Each dataclass has its own module:

- `AmmeterSettings`
- `NetworkSettings`
- `RuntimeSettings`
- `RunningEmulator`

Each operation extracted from the original `main.py` also has a dedicated
module:

- YAML loading
- Positive-number resolution
- Runtime configuration resolution
- Emulator serving
- Emulator startup
- Thread joining
- Emulator shutdown
- Measurement use case
- Console presentation
- Application composition

Protocol classes are similarly separated under `src/application/ports`.

## Compatibility

The refactor preserves:

- `main.main(config_path=..., emit=...)`
- `main.DEFAULT_CONFIG_PATH`
- `Ammeters.client.request_current_from_ammeter`
- `Ammeters.base_ammeter.AmmeterEmulatorBase`
- `src.utils.config.load_config`
- Measurement order and console formatting
- Startup, timeout, cleanup, and error-precedence behavior

The original `Ammeters` package remains in place as an infrastructure adapter.
Moving those emulators would add compatibility risk without improving the
application dependency direction.

## Architecture checks

`tests/test_architecture.py` prevents the main entry point from accumulating
configuration, threading, socket, or concrete-emulator responsibilities again.
It also verifies one dataclass/operation per selected module and prevents the
application layer from importing infrastructure implementations.
