"""Git command facade and parsers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ..constants import MAX_HISTORY_COMMITS
from ..models import BranchInfo, CommitInfo, FileChange, QuickSaveResult, RemoteInfo, SyncStatus
from ..utils.validation import validate_branch_name, validate_commit_message, validate_tag_name
from .history_parser import FIELD_SEPARATOR, RECORD_SEPARATOR, parse_git_log
from .process_service import ProcessService
from .status_parser import parse_porcelain_v1

_QUICK_SAVE_SUBJECT = re.compile(r"^Quick Save ([1-9]\d*)$")


class GitCommandError(RuntimeError):
    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


class GitService:
    def __init__(self, executable: str = "git", process: ProcessService | None = None) -> None:
        self.executable = executable
        self.process = process or ProcessService()

    def _run(self, arguments: list[str], cwd: str | Path | None = None, timeout: int | None = None):
        return self.process.run(self.executable, arguments, cwd, timeout)

    def _run_checked(self, arguments: list[str], cwd: str | Path | None = None, timeout: int | None = None):
        result = self._run(arguments, cwd, timeout)
        if not result.successful:
            raise GitCommandError(result.stderr or result.stdout or "Git command failed.", result.stderr)
        return result

    def version(self):
        return self._run(["--version"], timeout=10)

    def detect_root(self, path: str | Path) -> Path | None:
        candidate = Path(path).expanduser().resolve(strict=False)
        if candidate.is_file():
            candidate = candidate.parent
        result = self._run(["-C", str(candidate), "rev-parse", "--show-toplevel"], timeout=15)
        if not result.successful or not result.stdout:
            return None
        return Path(result.stdout).resolve(strict=False)

    def initialize(self, path: str | Path, branch: str = "main"):
        branch = validate_branch_name(branch)
        root = Path(path).expanduser().resolve(strict=False)
        result = self._run(["-C", str(root), "init", "-b", branch], timeout=30)
        if result.successful:
            return result
        fallback = self._run_checked(["-C", str(root), "init"], timeout=30)
        rename = self._run_checked(["-C", str(root), "branch", "-M", branch], timeout=30)
        return rename if rename.successful else fallback

    def config_get(self, key: str, cwd: str | Path | None = None, global_scope: bool = False) -> str:
        arguments = ["config"]
        if global_scope:
            arguments.append("--global")
        arguments.extend(["--get", key])
        result = self._run(arguments, cwd, timeout=10)
        return result.stdout.strip() if result.successful else ""

    def config_set(self, key: str, value: str, cwd: str | Path | None = None, global_scope: bool = False):
        arguments = ["config"]
        if global_scope:
            arguments.append("--global")
        arguments.extend([key, value])
        return self._run_checked(arguments, cwd, timeout=15)

    def active_branch(self, cwd: str | Path) -> str:
        result = self._run(["branch", "--show-current"], cwd, timeout=15)
        return result.stdout.strip() if result.successful else ""

    def status(self, cwd: str | Path) -> list[FileChange]:
        root = Path(cwd).resolve(strict=False)
        result = self._run_checked(["status", "--porcelain=v1", "--untracked-files=all"], root, timeout=30)
        return parse_porcelain_v1(result.stdout, root)

    def add(self, cwd: str | Path, paths: Iterable[str]):
        path_list = [str(item) for item in paths]
        if not path_list:
            raise GitCommandError("No files were selected for staging.")
        return self._run_checked(["add", "--", *path_list], cwd, timeout=120)

    def add_all(self, cwd: str | Path):
        return self._run_checked(["add", "--all"], cwd, timeout=120)

    def unstage(self, cwd: str | Path, paths: Iterable[str]):
        path_list = [str(item) for item in paths]
        if not path_list:
            raise GitCommandError("No files were selected for unstaging.")
        result = self._run(["restore", "--staged", "--", *path_list], cwd, timeout=120)
        if result.successful:
            return result
        return self._run_checked(["rm", "--cached", "--", *path_list], cwd, timeout=120)

    def unstage_all(self, cwd: str | Path):
        result = self._run(["reset", "HEAD", "--"], cwd, timeout=120)
        if result.successful:
            return result
        return self._run_checked(["rm", "-r", "--cached", "."], cwd, timeout=120)

    def discard(self, cwd: str | Path, paths: Iterable[str]):
        path_list = [str(item) for item in paths]
        if not path_list:
            raise GitCommandError("No files were selected for discard.")
        return self._run_checked(["restore", "--worktree", "--", *path_list], cwd, timeout=120)

    def staged_files(self, cwd: str | Path) -> list[str]:
        result = self._run_checked(["diff", "--cached", "--name-only"], cwd, timeout=30)
        return [line for line in result.stdout.splitlines() if line.strip()]

    def commit(self, cwd: str | Path, message: str, description: str = ""):
        title = validate_commit_message(message)
        arguments = ["commit", "-m", title]
        if description.strip():
            arguments.extend(["-m", description.strip()])
        return self._run_checked(arguments, cwd, timeout=180)

    def fetch(self, cwd: str | Path, remote: str = "origin"):
        return self._run_checked(["fetch", remote, "--prune"], cwd, timeout=900)

    def pull(self, cwd: str | Path):
        return self._run_checked(["pull", "--ff-only"], cwd, timeout=900)

    def push(self, cwd: str | Path, remote: str = "origin", branch: str | None = None, set_upstream: bool = False):
        arguments = ["push"]
        if set_upstream:
            arguments.append("-u")
        arguments.append(remote)
        if branch:
            arguments.append(branch)
        return self._run_checked(arguments, cwd, timeout=1800)

    def current_upstream(self, cwd: str | Path) -> str:
        result = self._run(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            cwd,
            timeout=15,
        )
        return result.stdout.strip() if result.successful else ""

    def _current_push_plan(self, cwd: str | Path, fallback_remote: str) -> tuple[str, str, str, bool]:
        branch = self.active_branch(cwd)
        if not branch:
            raise GitCommandError("Pushing requires an active branch and cannot run in detached HEAD.")

        remote_names = {remote.name for remote in self.remotes(cwd)}
        upstream_remote = self.config_get(f"branch.{branch}.remote", cwd)
        upstream_merge_ref = self.config_get(f"branch.{branch}.merge", cwd)
        if upstream_remote or upstream_merge_ref:
            if not upstream_remote or not upstream_merge_ref:
                raise GitCommandError(f"The upstream configuration for branch '{branch}' is incomplete.")
            if upstream_remote != "." and upstream_remote not in remote_names:
                raise GitCommandError(f"Upstream remote '{upstream_remote}' is not configured.")
            if not upstream_merge_ref.startswith("refs/heads/"):
                raise GitCommandError(
                    f"The upstream branch for '{branch}' is not a publishable remote branch."
                )
            return branch, upstream_remote, upstream_merge_ref, False

        if fallback_remote not in remote_names:
            raise GitCommandError(
                f"Remote '{fallback_remote}' is not configured. Connect a remote before pushing."
            )
        return branch, fallback_remote, f"refs/heads/{branch}", True

    def push_current(
        self,
        cwd: str | Path,
        fallback_remote: str = "origin",
        expected_branch: str = "",
    ):
        branch, remote, remote_ref, set_upstream = self._current_push_plan(cwd, fallback_remote)
        if expected_branch and branch != expected_branch:
            raise GitCommandError(
                f"The active branch changed from '{expected_branch}' to '{branch}' before push."
            )
        arguments = ["push"]
        if set_upstream:
            arguments.append("-u")
        arguments.extend([remote, f"{branch}:{remote_ref}"])
        return self._run_checked(arguments, cwd, timeout=1800)

    def next_quick_save_number(self, cwd: str | Path) -> int:
        result = self._run_checked(
            ["rev-list", "--all", "--no-commit-header", "--format=%s"],
            cwd,
            timeout=120,
        )
        highest = 0
        for subject in result.stdout.splitlines():
            match = _QUICK_SAVE_SUBJECT.fullmatch(subject)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    def quick_save(self, cwd: str | Path, remote: str = "origin") -> QuickSaveResult:
        root = Path(cwd).expanduser().resolve(strict=False)
        branch, _remote, _remote_ref, _set_upstream = self._current_push_plan(root, remote)

        conflicts = [change.path for change in self.status(root) if change.conflicted]
        if conflicts:
            raise GitCommandError("Resolve repository conflicts before using Quick Save.")

        self.add_all(root)
        if not self.staged_files(root):
            raise GitCommandError("There are no changes to quick save.")

        message = f"Quick Save {self.next_quick_save_number(root)}"
        commit_result = self.commit(root, message)
        try:
            push_result = self.push_current(root, remote, expected_branch=branch)
        except Exception as exc:
            raise GitCommandError(
                f"{message} was committed locally, but push failed: {exc}",
                getattr(exc, "stderr", ""),
            ) from exc

        return QuickSaveResult(
            message=message,
            branch=branch,
            commit=commit_result,
            push=push_result,
        )

    def sync(self, cwd: str | Path, remote: str = "origin"):
        self.fetch(cwd, remote)
        self.pull(cwd)
        return self.push(cwd, remote)

    def remotes(self, cwd: str | Path) -> list[RemoteInfo]:
        result = self._run_checked(["remote", "-v"], cwd, timeout=30)
        by_name: dict[str, RemoteInfo] = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            name, url, direction = parts[0], parts[1], parts[2].strip("()")
            remote = by_name.setdefault(name, RemoteInfo(name=name))
            if direction == "fetch":
                remote.fetch_url = url
            elif direction == "push":
                remote.push_url = url
        return list(by_name.values())

    def add_remote(self, cwd: str | Path, name: str, url: str):
        return self._run_checked(["remote", "add", name, url], cwd, timeout=30)

    def set_remote_url(self, cwd: str | Path, name: str, url: str):
        return self._run_checked(["remote", "set-url", name, url], cwd, timeout=30)

    def remove_remote(self, cwd: str | Path, name: str):
        return self._run_checked(["remote", "remove", name], cwd, timeout=30)

    def history(self, cwd: str | Path, max_count: int = MAX_HISTORY_COMMITS) -> list[CommitInfo]:
        pretty = (
            f"%H{FIELD_SEPARATOR}%P{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae"
            f"{FIELD_SEPARATOR}%aI{FIELD_SEPARATOR}%D{FIELD_SEPARATOR}%s"
            f"{FIELD_SEPARATOR}%b{RECORD_SEPARATOR}"
        )
        result = self._run(
            ["log", "--all", f"--max-count={max(1, min(max_count, 1000))}", f"--pretty=format:{pretty}"],
            cwd,
            timeout=120,
        )
        if not result.successful:
            return []
        return parse_git_log(result.stdout)

    def branches(self, cwd: str | Path) -> list[BranchInfo]:
        fmt = "%(HEAD)%00%(refname:short)%00%(upstream:short)%00%(objectname:short)%00%(subject)%00%(authorname)%00%(authordate:iso8601)"
        result = self._run_checked(["for-each-ref", "refs/heads", "refs/remotes", f"--format={fmt}"], cwd, timeout=60)
        branches: list[BranchInfo] = []
        for line in result.stdout.splitlines():
            fields = line.split("\x00")
            if len(fields) < 7:
                continue
            marker, name, upstream, short_hash, subject, author, authored_at = fields[:7]
            branches.append(
                BranchInfo(
                    name=name,
                    current=marker.strip() == "*",
                    remote=name.startswith("remotes/") or "/" in name and name.startswith(tuple(r.name + "/" for r in self.remotes(cwd))),
                    upstream=upstream,
                    short_hash=short_hash,
                    subject=subject,
                    author=author,
                    authored_at=authored_at,
                )
            )
        return branches

    def create_branch(self, cwd: str | Path, name: str, switch: bool = True):
        branch = validate_branch_name(name)
        arguments = ["switch", "-c", branch] if switch else ["branch", branch]
        return self._run_checked(arguments, cwd, timeout=60)

    def switch_branch(self, cwd: str | Path, name: str):
        branch = validate_branch_name(name)
        return self._run_checked(["switch", branch], cwd, timeout=300)

    def create_tag(self, cwd: str | Path, name: str, message: str = ""):
        tag = validate_tag_name(name)
        arguments = ["tag"]
        if message.strip():
            arguments.extend(["-a", tag, "-m", message.strip()])
        else:
            arguments.append(tag)
        return self._run_checked(arguments, cwd, timeout=60)

    def sync_status(self, cwd: str | Path) -> SyncStatus:
        upstream = self.current_upstream(cwd)
        if not upstream:
            return SyncStatus()
        counts = self._run(["rev-list", "--left-right", "--count", "HEAD...@{upstream}"], cwd, timeout=30)
        if not counts.successful:
            return SyncStatus(upstream=upstream)
        parts = counts.stdout.replace("\t", " ").split()
        ahead = int(parts[0]) if parts else 0
        behind = int(parts[1]) if len(parts) > 1 else 0
        return SyncStatus(upstream=upstream, ahead=ahead, behind=behind)
