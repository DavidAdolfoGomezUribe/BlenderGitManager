from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path


class ValidationError(ValueError):
    pass


_REF_INVALID = re.compile(r"[\x00-\x20~^:?*\\\[]")
_REPO_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_ref_name(value: str, label: str) -> str:
    name = value.strip()
    if not name:
        raise ValidationError(f"{label} cannot be empty.")
    if name.startswith("-") or name.startswith(".") or name.endswith("."):
        raise ValidationError(f"{label} cannot start with '-' or '.', or end with '.'.")
    if name.endswith(".lock") or ".." in name or "@{" in name:
        raise ValidationError(f"{label} contains a reserved Git sequence.")
    if _REF_INVALID.search(name):
        raise ValidationError(f"{label} contains characters that Git does not allow.")
    if "//" in name or name.endswith("/"):
        raise ValidationError(f"{label} contains an invalid slash sequence.")
    return name


def validate_branch_name(value: str) -> str:
    return _validate_ref_name(value, "Branch name")


def validate_tag_name(value: str) -> str:
    return _validate_ref_name(value, "Tag name")


def validate_repository_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValidationError("Repository name cannot be empty.")
    if not _REPO_NAME.fullmatch(name):
        raise ValidationError("Repository name may only contain letters, numbers, '.', '_' and '-'.")
    if name in {".", ".."}:
        raise ValidationError("Repository name is invalid.")
    return name



def validate_email(value: str) -> str:
    email = value.strip()
    if not _EMAIL.fullmatch(email):
        raise ValidationError("Git author email is invalid.")
    return email


def is_probable_blender_temporary_directory(path: str | Path) -> bool:
    directory = Path(path).expanduser().resolve(strict=False)
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=False)
    if directory == temporary_root:
        return True
    try:
        relative = directory.relative_to(temporary_root)
    except ValueError:
        return False
    name = relative.parts[0].lower() if relative.parts else ""
    return name.startswith(("blender", "recovery"))


def validate_commit_message(value: str) -> str:
    message = value.strip()
    if not message:
        raise ValidationError("Commit message cannot be empty.")
    if "\x00" in message:
        raise ValidationError("Commit message contains an invalid null character.")
    return message


def validate_writable_directory(path: str | Path, create: bool = False) -> Path:
    directory = Path(path).expanduser().resolve(strict=False)
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    if not directory.exists():
        raise ValidationError("The selected directory does not exist.")
    if not directory.is_dir():
        raise ValidationError("The selected path is not a directory.")
    if not os.access(directory, os.W_OK):
        raise ValidationError("The selected directory is not writable.")
    return directory
