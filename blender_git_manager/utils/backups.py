from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


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
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = destination_root / f"{source_path.stem}_backup_{stamp}{source_path.suffix}"
    shutil.copy2(source_path, destination)
    return destination
