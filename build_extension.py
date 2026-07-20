from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "blender_git_manager"
OUTPUT = ROOT / "dist" / "blender_git_manager-0.1.6.zip"
EXCLUDED_PARTS = {"__pycache__", ".git"}


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.rglob("*")):
            if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts) or path.suffix == ".pyc":
                continue
            archive.write(path, path.relative_to(SOURCE).as_posix())
    return OUTPUT


if __name__ == "__main__":
    print(build())
