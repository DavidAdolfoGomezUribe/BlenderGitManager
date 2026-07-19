from __future__ import annotations

from pathlib import Path


def normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def is_path_inside(child: str | Path, parent: str | Path) -> bool:
    child_path = normalize_path(child)
    parent_path = normalize_path(parent)
    try:
        child_path.relative_to(parent_path)
        return True
    except ValueError:
        return False


def relative_or_absolute(path: str | Path, root: str | Path) -> str:
    path_obj = normalize_path(path)
    root_obj = normalize_path(root)
    try:
        return path_obj.relative_to(root_obj).as_posix()
    except ValueError:
        return str(path_obj)
