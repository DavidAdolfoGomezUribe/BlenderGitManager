from __future__ import annotations

from pathlib import Path

from ..models import LFSFile
from .git_service import GitCommandError
from .process_service import ProcessService


class LFSService:
    def __init__(self, git_executable: str = "git", process: ProcessService | None = None) -> None:
        self.git_executable = git_executable
        self.process = process or ProcessService()

    def _run(self, arguments: list[str], cwd: str | Path | None = None, timeout: int | None = None):
        return self.process.run(self.git_executable, ["lfs", *arguments], cwd, timeout)

    def _run_checked(self, arguments: list[str], cwd: str | Path | None = None, timeout: int | None = None):
        result = self._run(arguments, cwd, timeout)
        if not result.successful:
            raise GitCommandError(result.stderr or result.stdout or "Git LFS command failed.")
        return result

    def version(self):
        return self._run(["version"], timeout=15)

    def initialize_local(self, cwd: str | Path):
        return self._run_checked(["install", "--local"], cwd, timeout=60)

    def environment(self, cwd: str | Path):
        return self._run(["env"], cwd, timeout=30)

    def is_active(self, cwd: str | Path) -> bool:
        return self.environment(cwd).successful

    def track(self, cwd: str | Path, pattern: str):
        clean = pattern.strip()
        if not clean or "\x00" in clean or "\n" in clean:
            raise ValueError("LFS pattern is invalid.")
        return self._run_checked(["track", clean], cwd, timeout=60)

    def untrack(self, cwd: str | Path, pattern: str):
        clean = pattern.strip()
        if not clean or "\x00" in clean or "\n" in clean:
            raise ValueError("LFS pattern is invalid.")
        return self._run_checked(["untrack", clean], cwd, timeout=60)

    def tracked_patterns(self, cwd: str | Path) -> list[str]:
        result = self._run(["track"], cwd, timeout=30)
        patterns: list[str] = []
        if not result.successful:
            return patterns
        for line in result.stdout.splitlines():
            if "(" in line and ")" in line:
                patterns.append(line.split("(", 1)[0].strip())
        return patterns

    def ls_files(self, cwd: str | Path) -> list[LFSFile]:
        result = self._run(["ls-files", "--long", "--size"], cwd, timeout=120)
        if not result.successful:
            return []
        files: list[LFSFile] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Typical output: <oid> * path (12 KB)
            oid, separator, rest = stripped.partition(" ")
            if not separator:
                continue
            marker = rest[:1]
            path_with_size = rest[2:] if len(rest) > 2 else ""
            path = path_with_size.rsplit(" (", 1)[0]
            files.append(LFSFile(oid=oid, path=path, pending=marker == "-"))
        return files

    def pull(self, cwd: str | Path):
        return self._run_checked(["pull"], cwd, timeout=1800)
