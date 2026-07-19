from __future__ import annotations

from datetime import datetime
from pathlib import Path

import bpy

from .constants import MAX_OUTPUT_LINES
from .preferences import get_addon_preferences
from .services import GitHubService, GitService, LFSService, RepositoryService
from .utils.formatting import format_bytes, redact_text


def append_output(
    context: bpy.types.Context,
    message: str,
    level: str = "INFO",
    *,
    echo_console: bool = True,
) -> None:
    state = context.scene.git_manager
    safe_level = level if level in {"INFO", "SUCCESS", "WARNING", "ERROR"} else "INFO"
    timestamp = datetime.now().strftime("%H:%M:%S")
    for raw_line in str(message).splitlines() or [""]:
        safe_message = redact_text(raw_line)[:2048]
        line = state.output_lines.add()
        line.timestamp = timestamp
        line.level = safe_level
        line.message = safe_message
        while len(state.output_lines) > MAX_OUTPUT_LINES:
            state.output_lines.remove(0)
        state.output_index = max(0, len(state.output_lines) - 1)
        if echo_console:
            try:
                print(
                    f"[Blender Git Manager][{timestamp}][{safe_level}] {safe_message}",
                    flush=True,
                )
            except (AttributeError, OSError, UnicodeError, ValueError):
                pass


def build_services(context: bpy.types.Context):
    preferences = get_addon_preferences(context)
    git = GitService(preferences.git_executable)
    lfs = LFSService(preferences.git_executable, git.process)
    github = GitHubService(preferences.gh_executable, git.process)
    repository = RepositoryService(git, lfs, github)
    return git, lfs, github, repository


def _version_line(output: str) -> str:
    return output.splitlines()[0].strip() if output else ""


def refresh_dependencies(context: bpy.types.Context) -> None:
    state = context.scene.git_manager
    git, lfs, github, _repository = build_services(context)

    git_result = git.version()
    state.git_installed = git_result.successful
    state.git_version = _version_line(git_result.stdout or git_result.stderr)

    lfs_result = lfs.version()
    state.lfs_installed = lfs_result.successful
    state.lfs_version = _version_line(lfs_result.stdout or lfs_result.stderr)

    gh_result = github.version()
    state.gh_installed = gh_result.successful
    state.gh_version = _version_line(gh_result.stdout or gh_result.stderr)

    if state.gh_installed:
        auth = github.auth_status()
        state.github_authenticated = auth.successful
        state.github_user = github.authenticated_user() if auth.successful else ""
    else:
        state.github_authenticated = False
        state.github_user = ""


def resolve_repository_root(context: bpy.types.Context) -> Path | None:
    state = context.scene.git_manager
    git, _lfs, _github, _repository = build_services(context)
    candidates: list[Path] = []
    if state.repository_path:
        candidates.append(Path(bpy.path.abspath(state.repository_path)))
    if bpy.data.filepath:
        candidates.append(Path(bpy.data.filepath).resolve().parent)
    for candidate in candidates:
        root = git.detect_root(candidate)
        if root:
            return root
    return None


def refresh_repository_state(context: bpy.types.Context, include_dependencies: bool = True) -> bool:
    state = context.scene.git_manager
    state.blend_unsaved = bool(bpy.data.is_dirty or not bpy.data.filepath)
    if include_dependencies:
        refresh_dependencies(context)
    if not state.git_installed:
        state.status_message = "Git is not installed or the executable path is invalid."
        return False

    root = resolve_repository_root(context)
    if not root:
        state.repository_name = ""
        state.active_branch = ""
        state.remote_url = ""
        state.changes.clear()
        state.commits.clear()
        state.branches.clear()
        state.status_message = "No Git repository detected."
        return False

    _git, lfs, _github, repository = build_services(context)
    try:
        snapshot = repository.snapshot(root, history_limit=100)
    except Exception as exc:
        state.status_message = str(exc)
        append_output(context, str(exc), "ERROR")
        return False

    state.repository_path = str(snapshot.root)
    state.repository_name = snapshot.name
    state.active_branch = snapshot.active_branch or "Detached HEAD"
    state.upstream = snapshot.sync.upstream
    state.ahead = snapshot.sync.ahead
    state.behind = snapshot.sync.behind
    state.sync_label = snapshot.sync.label
    state.lfs_active = snapshot.lfs_active
    state.remote_url = snapshot.remotes[0].fetch_url if snapshot.remotes else ""

    if snapshot.last_commit:
        state.last_commit_hash = snapshot.last_commit.short_hash
        state.last_commit_subject = snapshot.last_commit.subject
        state.last_commit_author = snapshot.last_commit.author_name
    else:
        state.last_commit_hash = ""
        state.last_commit_subject = "No commits yet"
        state.last_commit_author = ""

    lfs_paths = {item.path for item in lfs.ls_files(root)} if state.lfs_installed and state.lfs_active else set()

    state.changes.clear()
    for change in snapshot.changes:
        item = state.changes.add()
        item.index_status = change.index_status
        item.worktree_status = change.worktree_status
        item.status_code = change.status_code
        item.path = change.path
        item.original_path = change.original_path
        item.size_label = format_bytes(change.size_bytes)
        item.uses_lfs = change.path in lfs_paths
        item.staged = change.staged
        item.conflicted = change.conflicted
        item.untracked = change.untracked

    state.commits.clear()
    for commit in snapshot.commits:
        item = state.commits.add()
        item.full_hash = commit.full_hash
        item.short_hash = commit.short_hash
        item.subject = commit.subject
        item.body = commit.body
        item.author_name = commit.author_name
        item.author_email = commit.author_email
        item.authored_at = commit.authored_at
        item.decorations = commit.decorations
        item.parent_hashes = " ".join(commit.parent_hashes)
        item.is_merge = commit.is_merge

    state.branches.clear()
    for branch in snapshot.branches:
        item = state.branches.add()
        item.name = branch.name
        item.current = branch.current
        item.remote = branch.remote
        item.upstream = branch.upstream
        item.short_hash = branch.short_hash
        item.subject = branch.subject
        item.author = branch.author
        item.authored_at = branch.authored_at

    state.status_message = f"{len(state.changes)} changed file(s)"
    return True
