import os
from pathlib import Path


def publish_archive_without_overwrite(
    temporary_path: Path,
    target_path: Path,
) -> None:
    """Atomically publish a file without replacing an existing target."""
    if os.name == "nt":
        try:
            os.rename(temporary_path, target_path)
        except PermissionError as exc:
            if getattr(exc, "winerror", None) in (80, 183):
                raise FileExistsError(str(target_path)) from exc
            raise
        return
    os.link(temporary_path, target_path)
