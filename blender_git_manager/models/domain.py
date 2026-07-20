"""Domain models that are independent from Blender's Python API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(slots=True)
class CommandResult:
    executable: str
    arguments: tuple[str, ...]
    return_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False
    cancelled: bool = False

    @property
    def successful(self) -> bool:
        return self.return_code == 0 and not self.timed_out and not self.cancelled

    @property
    def best_output(self) -> str:
        return self.stdout or self.stderr


@dataclass(slots=True)
class QuickSaveResult:
    message: str
    branch: str
    commit: CommandResult
    push: CommandResult


@dataclass(slots=True)
class DependencyStatus:
    name: str
    executable: str
    installed: bool
    version: str = ""
    error: str = ""


@dataclass(slots=True)
class FileChange:
    index_status: str
    worktree_status: str
    path: str
    original_path: str = ""
    size_bytes: int = 0
    uses_lfs: bool = False

    @property
    def staged(self) -> bool:
        return self.index_status not in {" ", "?", "!"}

    @property
    def conflicted(self) -> bool:
        code = f"{self.index_status}{self.worktree_status}"
        return code in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}

    @property
    def untracked(self) -> bool:
        return self.index_status == "?" and self.worktree_status == "?"

    @property
    def status_code(self) -> str:
        return f"{self.index_status}{self.worktree_status}"


@dataclass(slots=True)
class CommitInfo:
    full_hash: str
    parent_hashes: tuple[str, ...]
    author_name: str
    author_email: str
    authored_at: str
    decorations: str
    subject: str
    body: str = ""

    @property
    def short_hash(self) -> str:
        return self.full_hash[:8]

    @property
    def is_merge(self) -> bool:
        return len(self.parent_hashes) > 1


@dataclass(slots=True)
class BranchInfo:
    name: str
    current: bool = False
    remote: bool = False
    upstream: str = ""
    short_hash: str = ""
    subject: str = ""
    author: str = ""
    authored_at: str = ""


@dataclass(slots=True)
class RemoteInfo:
    name: str
    fetch_url: str = ""
    push_url: str = ""


@dataclass(slots=True)
class SyncStatus:
    upstream: str = ""
    ahead: int = 0
    behind: int = 0

    @property
    def label(self) -> str:
        if not self.upstream:
            return "No upstream"
        if self.ahead == 0 and self.behind == 0:
            return "Up to date"
        return f"{self.ahead} ahead, {self.behind} behind"


@dataclass(slots=True)
class LFSFile:
    oid: str
    path: str
    size_bytes: int = 0
    pending: bool = False


@dataclass(slots=True)
class RepositorySnapshot:
    root: Path
    name: str
    active_branch: str
    remotes: tuple[RemoteInfo, ...] = ()
    changes: tuple[FileChange, ...] = ()
    commits: tuple[CommitInfo, ...] = ()
    branches: tuple[BranchInfo, ...] = ()
    sync: SyncStatus = field(default_factory=SyncStatus)
    lfs_active: bool = False
    last_commit: CommitInfo | None = None


StepState = Literal["pending", "running", "completed", "failed", "skipped"]


@dataclass(slots=True)
class InitStep:
    key: str
    label: str
    state: StepState = "pending"
    detail: str = ""


@dataclass(slots=True)
class InitConfig:
    repository_path: Path
    repository_name: str
    initial_branch: str = "main"
    author_name: str = ""
    author_email: str = ""
    apply_identity_globally: bool = False
    create_gitignore: bool = True
    overwrite_gitignore: bool = False
    enable_lfs: bool = True
    lfs_patterns: tuple[str, ...] = ("*.blend",)
    create_initial_commit: bool = True
    initial_commit_message: str = "Initial commit"
    stage_mode: Literal["ALL", "RECOMMENDED", "NONE"] = "ALL"
    connect_github: bool = False
    github_owner: str = ""
    github_visibility: Literal["private", "public"] = "private"
    github_description: str = ""
    remote_name: str = "origin"
    push_initial_branch: bool = True


@dataclass(slots=True)
class InitReport:
    repository_path: Path
    steps: list[InitStep]
    initial_commit_hash: str = ""
    remote_url: str = ""

    @property
    def successful(self) -> bool:
        return not any(step.state == "failed" for step in self.steps)
