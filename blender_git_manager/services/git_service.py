"""Git command facade and parsers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ..constants import MAX_HISTORY_COMMITS
from ..models import BranchInfo, CommandResult, CommitInfo, FileChange, QuickSaveResult, RemoteInfo, SyncStatus
from ..utils.validation import validate_branch_name, validate_commit_message, validate_tag_name
from .history_parser import FIELD_SEPARATOR, RECORD_SEPARATOR, parse_git_log
from .lfs_push_failures import LFSFailureKind, classify_lfs_push_failure, extract_github_locksverify_key
from .process_service import ProcessService
from .status_parser import parse_porcelain_v1

_QUICK_SAVE_SUBJECT = re.compile(r"^Quick Save ([1-9]\d*)$")
_FULL_OBJECT_ID = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z", re.ASCII)


class GitCommandError(RuntimeError):
    def __init__(
        self,
        message: str,
        stderr: str = "",
        attempts: tuple[CommandResult, ...] = (),
    ) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.attempts = attempts


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

    def head_branch(self, cwd: str | Path) -> str:
        """Return the attached local branch, distinguishing detached HEAD from Git errors."""
        result = self._run_checked(
            [
                "status",
                "--porcelain=v2",
                "--branch",
                "-z",
                "--untracked-files=no",
                "--",
                ":(exclude)**",
            ],
            cwd,
            timeout=30,
        )
        for record in result.stdout.split("\x00"):
            if not record.startswith("# branch.head "):
                continue
            branch = record.removeprefix("# branch.head ")
            if branch == "(detached)":
                return ""
            return validate_branch_name(branch)
        raise GitCommandError("Git did not report the current HEAD branch.")

    @staticmethod
    def _validated_object_id(value: str, *, label: str = "Commit") -> str:
        object_id = str(value)
        if not _FULL_OBJECT_ID.fullmatch(object_id):
            raise GitCommandError(
                f"{label} must be a full 40- or 64-character hexadecimal object ID."
            )
        return object_id.lower()

    def resolve_commit(self, cwd: str | Path, commit: str) -> str:
        """Resolve a full object ID and verify that it names a commit."""
        object_id = self._validated_object_id(commit)
        result = self._run_checked(
            [
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{object_id}^{{commit}}",
            ],
            cwd,
            timeout=30,
        )
        return self._validated_object_id(result.stdout.strip(), label="Resolved commit")

    def head_commit(self, cwd: str | Path) -> str:
        """Return the exact commit checked out at HEAD, or empty for an unborn HEAD."""
        result = self._run(
            [
                "rev-parse",
                "--verify",
                "--end-of-options",
                "HEAD^{commit}",
            ],
            cwd,
            timeout=30,
        )
        if not result.successful:
            symbolic = self._run(
                ["symbolic-ref", "--quiet", "HEAD"],
                cwd,
                timeout=15,
            )
            reference = symbolic.stdout.strip()
            if symbolic.successful and reference.startswith("refs/heads/"):
                validate_branch_name(reference.removeprefix("refs/heads/"))
                return ""
            raise GitCommandError(
                result.stderr or result.stdout or "Could not resolve the commit at HEAD.",
                result.stderr,
            )
        return self._validated_object_id(result.stdout.strip(), label="HEAD")

    def branch_head_commit(self, cwd: str | Path, branch_name: str) -> str:
        """Resolve the exact commit at a validated local branch ref."""
        branch = validate_branch_name(branch_name)
        result = self._run_checked(
            [
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"refs/heads/{branch}^{{commit}}",
            ],
            cwd,
            timeout=30,
        )
        return self._validated_object_id(
            result.stdout.strip(),
            label=f"Branch '{branch}' HEAD",
        )

    def commit_info(self, cwd: str | Path, commit: str) -> CommitInfo:
        """Read metadata for one exact commit, independent of ``log --all`` ordering."""
        object_id = self.resolve_commit(cwd, commit)
        pretty = (
            f"%H{FIELD_SEPARATOR}%P{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae"
            f"{FIELD_SEPARATOR}%aI{FIELD_SEPARATOR}%D{FIELD_SEPARATOR}%s"
            f"{FIELD_SEPARATOR}%b{RECORD_SEPARATOR}"
        )
        result = self._run_checked(
            [
                "log",
                "-1",
                f"--pretty=format:{pretty}",
                object_id,
                "--",
            ],
            cwd,
            timeout=30,
        )
        commits = parse_git_log(result.stdout)
        if not commits:
            raise GitCommandError(f"Git returned no metadata for commit {object_id}.")
        info = commits[0]
        parsed_id = self._validated_object_id(
            info.full_hash,
            label="Commit metadata",
        )
        if parsed_id != object_id:
            raise GitCommandError(
                f"Git returned metadata for {parsed_id} instead of requested commit {object_id}."
            )
        return info

    def checkout_commit(self, cwd: str | Path, commit: str):
        """Materialize one exact commit in detached-HEAD mode."""
        object_id = self.resolve_commit(cwd, commit)
        return self._run_checked(
            ["switch", "--detach", object_id],
            cwd,
            timeout=300,
        )

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
        return self._push_checked(arguments, cwd)

    @staticmethod
    def _combined_attempt_output(attempts: list[CommandResult]) -> str:
        sections: list[str] = []
        for index, result in enumerate(attempts, start=1):
            streams: list[str] = []
            if result.stdout:
                streams.append(f"[stdout]\n{result.stdout}")
            if result.stderr:
                streams.append(f"[stderr]\n{result.stderr}")
            if streams:
                sections.append(f"[Push attempt {index}]\n" + "\n".join(streams))
        return "\n\n".join(sections)

    def _push_checked(self, arguments: list[str], cwd: str | Path):
        attempts: list[CommandResult] = []
        lock_fallback_used = False
        transient_retry_used = False
        effective_arguments = list(arguments)

        while len(attempts) < 3:
            result = self._run(effective_arguments, cwd, timeout=1800)
            attempts.append(result)
            if result.successful:
                if lock_fallback_used:
                    self.process.emit_status(
                        "WARNING",
                        "[git-lfs] Push succeeded after temporarily skipping unavailable lock verification.",
                    )
                if transient_retry_used:
                    self.process.emit_status(
                        "WARNING",
                        "[git-lfs] Push succeeded after retrying a temporary GitHub LFS server error.",
                    )
                return result

            failure = classify_lfs_push_failure(result)
            if failure == LFSFailureKind.LOCK_VERIFY and not lock_fallback_used:
                output = "\n".join(part for part in (result.stderr, result.stdout) if part)
                key = extract_github_locksverify_key(output)
                if key:
                    effective_arguments = ["-c", f"{key}=false", *arguments]
                    lock_fallback_used = True
                    self.process.emit_status(
                        "WARNING",
                        "[git-lfs] Retrying the same push once with lock verification disabled "
                        "only for this invocation.",
                    )
                    continue

            if failure == LFSFailureKind.TRANSIENT_BATCH and not transient_retry_used:
                self.process.emit_status(
                    "WARNING",
                    "[git-lfs] GitHub LFS returned a temporary batch error. Retrying the same push once in 2 seconds.",
                )
                if self.process.wait_for_retry(2.0):
                    transient_retry_used = True
                    continue
            break

        combined = self._combined_attempt_output(attempts)
        final_failure = classify_lfs_push_failure(attempts[-1])
        if transient_retry_used and final_failure == LFSFailureKind.TRANSIENT_BATCH:
            raise GitCommandError(
                "GitHub LFS is still returning a temporary server error after the automatic retry. "
                "Your commits remain local; use Push to try again later.",
                combined,
                tuple(attempts),
            )
        if len(attempts) > 1:
            raise GitCommandError(
                "Push failed after the automatic Git LFS recovery attempt. Review Git Output for details.",
                combined,
                tuple(attempts),
            )
        result = attempts[-1]
        raise GitCommandError(
            result.stderr or result.stdout or "Git push failed.",
            result.stderr,
            tuple(attempts),
        )

    def current_upstream(self, cwd: str | Path) -> str:
        result = self._run(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            cwd,
            timeout=15,
        )
        return result.stdout.strip() if result.successful else ""

    def _current_push_plan(self, cwd: str | Path, fallback_remote: str) -> tuple[str, str, str, bool]:
        branch = self.head_branch(cwd)
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
        return self._push_checked(arguments, cwd)

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
                getattr(exc, "attempts", ()),
            ) from exc

        return QuickSaveResult(
            message=message,
            branch=branch,
            commit=commit_result,
            push=push_result,
        )

    def sync(self, cwd: str | Path, remote: str = "origin"):
        self.fetch(cwd, remote)
        if self.current_upstream(cwd):
            self.pull(cwd)
        return self.push_current(cwd, remote)

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

    def branch_contains_regular_file(
        self,
        cwd: str | Path,
        branch_name: str,
        path: str | Path,
    ) -> bool:
        branch = validate_branch_name(branch_name)
        root = Path(cwd).expanduser().resolve(strict=False)
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else root / candidate
        try:
            relative = absolute.expanduser().resolve(strict=False).relative_to(root).as_posix()
        except ValueError as exc:
            raise GitCommandError("The Blender file must be inside the active repository.") from exc
        if not relative or relative == ".":
            raise GitCommandError("A repository-relative file path is required.")

        result = self._run_checked(
            [
                "--literal-pathspecs",
                "ls-tree",
                "-r",
                "-z",
                f"refs/heads/{branch}",
                "--",
                relative,
            ],
            root,
            timeout=30,
        )
        for record in result.stdout.split("\x00"):
            if not record or "\t" not in record:
                continue
            metadata, entry_path = record.split("\t", 1)
            fields = metadata.split()
            if (
                entry_path == relative
                and len(fields) >= 2
                and fields[0] in {"100644", "100755"}
                and fields[1] == "blob"
            ):
                return True
        return False

    def _commit_tree_entries(
        self,
        cwd: str | Path,
        commit: str,
    ) -> tuple[tuple[str, str, str], ...]:
        object_id = self.resolve_commit(cwd, commit)
        root = Path(cwd).expanduser().resolve(strict=False)
        result = self._run_checked(
            ["ls-tree", "-r", "-z", object_id],
            root,
            timeout=60,
        )
        entries: list[tuple[str, str, str]] = []
        for record in result.stdout.split("\x00"):
            if not record or "\t" not in record:
                continue
            metadata, path = record.split("\t", 1)
            fields = metadata.split()
            if len(fields) >= 3 and path:
                entries.append((fields[0], fields[1], path))
        return tuple(entries)

    def commit_tree_paths(self, cwd: str | Path, commit: str) -> tuple[str, ...]:
        """Return every exact leaf path tracked by one commit."""
        return tuple(path for _mode, _kind, path in self._commit_tree_entries(cwd, commit))

    def checkout_added_file_paths(
        self,
        cwd: str | Path,
        source_commit: str,
        target_commit: str,
    ) -> tuple[str, ...]:
        """Return target regular/symlink leaves with no exact source-tree entry."""
        source_paths = {
            path for _mode, _kind, path in self._commit_tree_entries(cwd, source_commit)
        }
        target_files = {
            path
            for mode, kind, path in self._commit_tree_entries(cwd, target_commit)
            if kind == "blob" and mode in {"100644", "100755", "120000"}
        }
        return tuple(sorted(target_files - source_paths))

    def commit_contains_regular_file(
        self,
        cwd: str | Path,
        commit: str,
        path: str | Path,
    ) -> bool:
        object_id = self.resolve_commit(cwd, commit)
        root = Path(cwd).expanduser().resolve(strict=False)
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else root / candidate
        try:
            relative = absolute.expanduser().resolve(strict=False).relative_to(root).as_posix()
        except ValueError as exc:
            raise GitCommandError("The Blender file must be inside the active repository.") from exc
        if not relative or relative == ".":
            raise GitCommandError("A repository-relative file path is required.")

        result = self._run_checked(
            [
                "--literal-pathspecs",
                "ls-tree",
                "-r",
                "-z",
                object_id,
                "--",
                relative,
            ],
            root,
            timeout=30,
        )
        for record in result.stdout.split("\x00"):
            if not record or "\t" not in record:
                continue
            metadata, entry_path = record.split("\t", 1)
            fields = metadata.split()
            if (
                entry_path == relative
                and len(fields) >= 2
                and fields[0] in {"100644", "100755"}
                and fields[1] == "blob"
            ):
                return True
        return False

    def repository_has_changes(self, cwd: str | Path) -> bool:
        """Return whether any staged, unstaged, conflicted, or untracked path exists."""
        root = Path(cwd).expanduser().resolve(strict=False)
        result = self._run_checked(
            [
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ],
            root,
            timeout=30,
        )
        return bool(result.stdout)

    def path_has_changes(self, cwd: str | Path, path: str | Path) -> bool:
        root = Path(cwd).expanduser().resolve(strict=False)
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else root / candidate
        try:
            relative = absolute.expanduser().resolve(strict=False).relative_to(root).as_posix()
        except ValueError as exc:
            raise GitCommandError("The Blender file must be inside the active repository.") from exc
        if not relative or relative == ".":
            raise GitCommandError("A repository-relative file path is required.")

        result = self._run_checked(
            [
                "--literal-pathspecs",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                relative,
            ],
            root,
            timeout=30,
        )
        return bool(result.stdout)

    def restore_path_from_branch(
        self,
        cwd: str | Path,
        branch_name: str,
        path: str | Path,
    ):
        branch = validate_branch_name(branch_name)
        root = Path(cwd).expanduser().resolve(strict=False)
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else root / candidate
        try:
            relative = absolute.expanduser().resolve(strict=False).relative_to(root).as_posix()
        except ValueError as exc:
            raise GitCommandError("The Blender file must be inside the active repository.") from exc
        if not relative or relative == ".":
            raise GitCommandError("A repository-relative file path is required.")
        return self._run_checked(
            [
                "--literal-pathspecs",
                "restore",
                "--source",
                f"refs/heads/{branch}",
                "--staged",
                "--worktree",
                "--",
                relative,
            ],
            root,
            timeout=300,
        )

    def restore_path_from_commit(
        self,
        cwd: str | Path,
        commit: str,
        path: str | Path,
    ):
        object_id = self.resolve_commit(cwd, commit)
        root = Path(cwd).expanduser().resolve(strict=False)
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else root / candidate
        try:
            relative = absolute.expanduser().resolve(strict=False).relative_to(root).as_posix()
        except ValueError as exc:
            raise GitCommandError("The Blender file must be inside the active repository.") from exc
        if not relative or relative == ".":
            raise GitCommandError("A repository-relative file path is required.")
        return self._run_checked(
            [
                "--literal-pathspecs",
                "restore",
                "--source",
                object_id,
                "--staged",
                "--worktree",
                "--",
                relative,
            ],
            root,
            timeout=300,
        )

    def restore_tree_from_commit(self, cwd: str | Path, commit: str):
        """Restore all tracked index/worktree paths from one exact commit."""
        object_id = self.resolve_commit(cwd, commit)
        root = Path(cwd).expanduser().resolve(strict=False)
        return self._run_checked(
            [
                "--literal-pathspecs",
                "restore",
                "--source",
                object_id,
                "--staged",
                "--worktree",
                "--",
                ".",
            ],
            root,
            timeout=600,
        )

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
