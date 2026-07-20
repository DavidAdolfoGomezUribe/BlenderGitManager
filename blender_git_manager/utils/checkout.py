from __future__ import annotations

import os
import stat
from pathlib import Path
from pathlib import PurePosixPath


def repository_has_checkout_changes(git, repository_path: str | Path) -> bool:
    """Return user-visible changes, excluding only legacy 0.1.5 internal backups."""
    for change in git.status(repository_path):
        normalized = change.path.replace("\\", "/")
        if normalized.startswith("./"):
            normalized = normalized[2:]
        legacy_backup = normalized == ".blender_git_backups" or normalized.startswith(
            ".blender_git_backups/"
        )
        if not (change.untracked and legacy_backup):
            return True
    return False


def _literal_worktree_path(repository_root: Path, relative_path: str) -> Path:
    pure_path = PurePosixPath(relative_path)
    if (
        not relative_path
        or pure_path.is_absolute()
        or any(part in {"", ".", ".."} for part in pure_path.parts)
    ):
        raise RuntimeError(f"Git returned an unsafe checkout path: {relative_path!r}")
    candidate = repository_root.joinpath(*pure_path.parts)
    resolved_parent = candidate.parent.resolve(strict=False)
    try:
        resolved_parent.relative_to(repository_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Checkout path escapes the repository through a linked directory: {relative_path}"
        ) from exc
    return candidate


def plan_checkout_cleanup(
    repository_root: str | Path,
    source_tree_paths: tuple[str, ...],
    target_added_paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Capture target-only leaves proven absent before checkout."""
    root = Path(repository_root).expanduser().resolve(strict=False)
    source_paths = set(source_tree_paths)
    cleanup_paths: list[str] = []
    for relative_path in target_added_paths:
        candidate = _literal_worktree_path(root, relative_path)
        if not os.path.lexists(candidate):
            cleanup_paths.append(relative_path)
            continue
        source_directory = f"{relative_path.rstrip('/')}/"
        if (
            candidate.is_dir()
            and not candidate.is_symlink()
            and any(path.startswith(source_directory) for path in source_paths)
        ):
            continue
        raise RuntimeError(
            f"Commit checkout would overwrite an existing untracked or ignored path: "
            f"{relative_path}"
        )
    return tuple(cleanup_paths)


def remove_checkout_created_paths(
    repository_root: str | Path,
    relative_paths: tuple[str, ...],
) -> None:
    """Remove only target-tree leaves that were proven absent before checkout."""
    root = Path(repository_root).expanduser().resolve(strict=False)
    for relative_path in sorted(
        relative_paths,
        key=lambda value: len(PurePosixPath(value).parts),
        reverse=True,
    ):
        candidate = _literal_worktree_path(root, relative_path)
        try:
            mode = os.lstat(candidate).st_mode
        except (FileNotFoundError, NotADirectoryError):
            continue
        if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
            raise RuntimeError(
                f"Rollback refused to remove a non-file checkout path: {relative_path}"
            )
        os.unlink(candidate)
