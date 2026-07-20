from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path


def checkout_backup_directory(
    repository_root: str | Path,
    config_root: str | Path,
) -> Path:
    repository = Path(repository_root).expanduser().resolve(strict=False)
    key = hashlib.sha256(
        str(repository).casefold().encode("utf-8", errors="replace")
    ).hexdigest()[:12]
    return (
        Path(config_root).expanduser().resolve(strict=False)
        / "blender_git_manager"
        / "backups"
        / f"{repository.name}-{key}"
    )


def create_timestamped_backup(source: str | Path, destination_directory: str | Path | None = None) -> Path:
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    destination_root = (
        Path(destination_directory).expanduser().resolve()
        if destination_directory
        else source_path.parent / ".blender_git_backups"
    )
    destination_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = destination_root / f"{source_path.stem}_backup_{stamp}{source_path.suffix}"
    shutil.copy2(source_path, destination)
    return destination
