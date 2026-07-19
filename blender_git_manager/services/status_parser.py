from __future__ import annotations

import shlex
from pathlib import Path

from ..models import FileChange


def _decode_path(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            parsed = shlex.split(value)
            return parsed[0] if parsed else value.strip('"')
        except ValueError:
            return value.strip('"')
    return value


def parse_porcelain_v1(output: str, repository_root: str | Path | None = None) -> list[FileChange]:
    root = Path(repository_root) if repository_root else None
    changes: list[FileChange] = []
    for line in output.splitlines():
        if len(line) < 3:
            continue
        index_status = line[0]
        worktree_status = line[1]
        raw_path = line[3:]
        original_path = ""
        if " -> " in raw_path:
            original_path, raw_path = raw_path.split(" -> ", 1)
            original_path = _decode_path(original_path)
        path = _decode_path(raw_path)
        size = 0
        if root:
            try:
                full_path = root / path
                if full_path.is_file():
                    size = full_path.stat().st_size
            except OSError:
                size = 0
        changes.append(
            FileChange(
                index_status=index_status,
                worktree_status=worktree_status,
                path=path,
                original_path=original_path,
                size_bytes=size,
            )
        )
    return changes
