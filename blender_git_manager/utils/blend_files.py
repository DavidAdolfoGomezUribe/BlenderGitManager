"""Validation helpers for safely reloading Blender files after a Git checkout."""

from __future__ import annotations

from pathlib import Path

_BLENDER_HEADER = b"BLENDER"
_GZIP_HEADER = b"\x1f\x8b"
_ZSTD_HEADER = b"\x28\xb5\x2f\xfd"
_GIT_LFS_POINTER_HEADER = b"version https://git-lfs.github.com/spec/v1"


class BlendFileValidationError(RuntimeError):
    pass


def validate_blend_file_for_reload(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve(strict=False)
    if not path.is_file():
        raise BlendFileValidationError(f"The Blender file does not exist in the selected branch: {path}")
    try:
        with path.open("rb") as stream:
            header = stream.read(64)
    except OSError as exc:
        raise BlendFileValidationError(f"The Blender file could not be read: {exc}") from exc
    if header.startswith(_GIT_LFS_POINTER_HEADER):
        raise BlendFileValidationError(
            "The Blender file is still a Git LFS pointer. Pull its LFS object before reloading."
        )
    if not header.startswith((_BLENDER_HEADER, _GZIP_HEADER, _ZSTD_HEADER)):
        raise BlendFileValidationError("The checked-out file is not a valid Blender file.")
    return path
