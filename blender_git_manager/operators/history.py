from __future__ import annotations

from pathlib import Path

import bpy
from bpy.props import IntProperty, StringProperty

from ..preferences import get_addon_preferences
from ..state_sync import append_output, build_services, refresh_repository_state
from ..utils.backups import checkout_backup_directory, create_timestamped_backup
from ..utils.blend_files import validate_blend_file_for_reload
from ..utils.checkout import (
    plan_checkout_cleanup,
    remove_checkout_created_paths,
    repository_has_checkout_changes,
)
from ..utils.paths import is_path_inside
from .base import reject_if_task_running

_pending_commit_reload: tuple[str, str, str] | None = None
_RELOAD_TASK_LABEL = "Reloading Blender file from commit"
_DEPENDENCY_STATE_FIELDS = (
    "git_installed",
    "git_version",
    "lfs_installed",
    "lfs_version",
    "gh_installed",
    "gh_version",
    "github_authenticated",
    "github_user",
)


def is_commit_reload_pending() -> bool:
    return _pending_commit_reload is not None


def _set_reload_task_state(active: bool) -> None:
    try:
        state = bpy.context.scene.git_manager
    except (AttributeError, RuntimeError):
        return
    if active:
        state.task_running = True
        state.task_label = _RELOAD_TASK_LABEL
    elif state.task_label == _RELOAD_TASK_LABEL:
        state.task_running = False
        state.task_label = ""


def _append_reload_message(message: str, level: str) -> None:
    try:
        append_output(bpy.context, message, level)
    except Exception:
        print(f"[Blender Git Manager][{level}] {message}", flush=True)


def _clear_pending_commit_reload(token: tuple[str, str, str]) -> None:
    global _pending_commit_reload
    if _pending_commit_reload == token:
        _pending_commit_reload = None
        _set_reload_task_state(False)


def cancel_pending_commit_reload() -> None:
    global _pending_commit_reload
    _pending_commit_reload = None
    _set_reload_task_state(False)


def _begin_commit_reload(
    filepath: Path,
    repository_path: Path,
    commit_hash: str,
) -> tuple[str, str, str]:
    global _pending_commit_reload
    token = (str(filepath), str(repository_path), str(commit_hash))
    if _pending_commit_reload is not None:
        raise RuntimeError("Another commit file reload is already pending.")
    _pending_commit_reload = token
    _set_reload_task_state(True)
    return token


def _select_history_commit(state, commit_hash: str) -> bool:
    state.active_tab = "HISTORY"
    for index, commit in enumerate(state.commits):
        if commit.full_hash == commit_hash:
            state.commits_index = index
            return True
    return False


def _refresh_after_failed_reload(repository_path: str, expected_filepath: str | Path) -> None:
    try:
        fresh_context = bpy.context
        current_path = (
            Path(bpy.data.filepath).expanduser().resolve(strict=False)
            if bpy.data.filepath
            else None
        )
        expected_path = Path(expected_filepath).expanduser().resolve(strict=False)
        if current_path != expected_path:
            return
        fresh_context.scene.git_manager.repository_path = repository_path
        refresh_repository_state(fresh_context, include_dependencies=False)
    except Exception:
        pass


def _reload_blend_from_commit(
    filepath: str,
    repository_path: str,
    commit_hash: str,
) -> tuple[bool, str]:
    """Reload immediately, without yielding a saveable stale scene after checkout."""
    token = (filepath, repository_path, commit_hash)
    if _pending_commit_reload != token:
        return False, "Discarded an outdated Blender commit reload request."

    try:
        expected_path = Path(filepath).expanduser().resolve(strict=False)
        current_path = (
            Path(bpy.data.filepath).expanduser().resolve(strict=False)
            if bpy.data.filepath
            else None
        )
        if current_path != expected_path:
            raise RuntimeError("The active Blender file changed before reloading.")
        if bpy.data.is_dirty:
            raise RuntimeError("The Blender file became dirty before reloading.")

        git, _lfs, _github, _repository = build_services(bpy.context)
        if git.head_branch(repository_path):
            raise RuntimeError("Git is not in detached HEAD after loading the commit.")
        if git.head_commit(repository_path) != commit_hash:
            raise RuntimeError("Git HEAD changed before Blender could reload the commit.")
        if repository_has_checkout_changes(git, repository_path):
            raise RuntimeError("The repository changed on disk before Blender could reload.")

        validate_blend_file_for_reload(expected_path)
        dependency_state = {
            field: getattr(bpy.context.scene.git_manager, field)
            for field in _DEPENDENCY_STATE_FIELDS
        }
        result = bpy.ops.wm.open_mainfile(
            filepath=str(expected_path),
            load_ui=False,
            use_scripts=False,
            display_file_selector=False,
        )
        if "FINISHED" not in result:
            raise RuntimeError("Blender cancelled the file reload.")
    except Exception as exc:
        return False, str(exc)

    try:
        fresh_context = bpy.context
        fresh_state = fresh_context.scene.git_manager
        fresh_state.task_running = False
        fresh_state.task_label = ""
        for field, value in dependency_state.items():
            setattr(fresh_state, field, value)
        fresh_state.repository_path = repository_path
        refresh_repository_state(fresh_context, include_dependencies=False)
        _select_history_commit(fresh_state, commit_hash)
        append_output(
            fresh_context,
            f"Loaded commit {commit_hash[:8]} and reloaded {expected_path.name}. "
            "HEAD is detached; switch to a branch or create one before committing.",
            "SUCCESS",
        )
    except Exception as exc:
        _append_reload_message(
            f"Reloaded {expected_path.name} from commit {commit_hash[:8]}, "
            f"but repository status could not be refreshed: {exc}",
            "WARNING",
        )
    finally:
        _clear_pending_commit_reload(token)
    return True, ""


def _restore_source_after_reload_failure(
    git,
    repository_path: Path,
    blend_path: Path,
    source_branch: str,
    source_commit: str,
    target_commit: str,
    cleanup_paths: tuple[str, ...],
) -> tuple[bool, str]:
    command_warnings: list[str] = []
    source_label = f"branch '{source_branch}'" if source_branch else f"detached HEAD {source_commit[:8]}"

    def transition_to_source() -> None:
        if source_branch:
            git.switch_branch(repository_path, source_branch)
        else:
            git.checkout_commit(repository_path, source_commit)

    try:
        current_branch = git.head_branch(repository_path)
        current_commit = git.head_commit(repository_path)
        already_at_source = current_commit == source_commit and current_branch == source_branch
        at_target = current_commit == target_commit and not current_branch
        if not already_at_source:
            if not at_target:
                raise RuntimeError(
                    "automatic rollback found Git at an unexpected branch or commit"
                )
            try:
                transition_to_source()
            except Exception as exc:
                command_warnings.append(str(exc))
                current_branch = git.head_branch(repository_path)
                current_commit = git.head_commit(repository_path)
                if current_commit == target_commit and not current_branch:
                    git.restore_tree_from_commit(repository_path, source_commit)
                    remove_checkout_created_paths(repository_path, cleanup_paths)
                    try:
                        transition_to_source()
                    except Exception as retry_exc:
                        command_warnings.append(str(retry_exc))

        current_branch = git.head_branch(repository_path)
        current_commit = git.head_commit(repository_path)
        if current_branch != source_branch or current_commit != source_commit:
            raise RuntimeError(f"Git did not return to {source_label}")

        if repository_has_checkout_changes(git, repository_path):
            git.restore_tree_from_commit(repository_path, source_commit)
        remove_checkout_created_paths(repository_path, cleanup_paths)
        if repository_has_checkout_changes(git, repository_path):
            raise RuntimeError(
                "repository files are still modified after whole-tree rollback; inspect Git status"
            )
        validate_blend_file_for_reload(blend_path)
        _refresh_after_failed_reload(str(repository_path), blend_path)
    except Exception as exc:
        warnings = (
            f" Git reported during rollback: {' | '.join(command_warnings)}"
            if command_warnings
            else ""
        )
        return False, f"Automatic rollback to {source_label} failed: {exc}.{warnings}"
    warnings = (
        f" Git reported during rollback: {' | '.join(command_warnings)}"
        if command_warnings
        else ""
    )
    return True, f"Restored {source_label} after the failure.{warnings}"


class GITMANAGER_OT_checkout_commit(bpy.types.Operator):
    bl_idname = "git_manager.checkout_commit"
    bl_label = "Load Commit"
    bl_description = (
        "Check out this commit in detached HEAD and reload the current Blender file"
    )

    commit_hash: StringProperty(options={"SKIP_SAVE"})
    commit_index: IntProperty(default=-1, options={"SKIP_SAVE"})

    def execute(self, context):
        state = context.scene.git_manager
        if _pending_commit_reload is not None:
            self.report({"WARNING"}, "Wait for the current commit file reload to finish.")
            return {"CANCELLED"}
        if reject_if_task_running(self, context):
            return {"CANCELLED"}
        if bpy.data.is_dirty or not bpy.data.filepath:
            self.report({"ERROR"}, "Save the current Blender file before loading a commit.")
            return {"CANCELLED"}
        if not state.repository_path:
            self.report({"ERROR"}, "Open a repository before loading a commit.")
            return {"CANCELLED"}

        requested_hash = self.commit_hash.strip().lower()
        if self.commit_index >= 0:
            if self.commit_index >= len(state.commits):
                self.report({"ERROR"}, "Commit history changed; select the commit again.")
                return {"CANCELLED"}
            indexed_hash = state.commits[self.commit_index].full_hash.strip().lower()
            if indexed_hash != requested_hash:
                self.report({"ERROR"}, "Commit history changed; select the commit again.")
                return {"CANCELLED"}

        blend_path = Path(bpy.data.filepath).expanduser().resolve(strict=False)
        git, _lfs, _github, _repository = build_services(context)
        repository_root = git.detect_root(state.repository_path)
        blend_repository_root = git.detect_root(blend_path.parent)
        if (
            repository_root is None
            or blend_repository_root is None
            or repository_root != blend_repository_root
            or not is_path_inside(blend_path, repository_root)
        ):
            self.report({"ERROR"}, "The current Blender file must be inside the active repository.")
            return {"CANCELLED"}

        relative_blend_path = blend_path.relative_to(repository_root)
        try:
            target_commit = git.resolve_commit(repository_root, requested_hash)
            source_branch = git.head_branch(repository_root)
            source_commit = git.head_commit(repository_root)
            if repository_has_checkout_changes(git, repository_root):
                raise RuntimeError(
                    "The repository has uncommitted changes. Commit or discard every changed "
                    "file before loading a historical commit."
                )
            cleanup_paths = plan_checkout_cleanup(
                repository_root,
                git.commit_tree_paths(repository_root, source_commit),
                git.checkout_added_file_paths(
                    repository_root,
                    source_commit,
                    target_commit,
                ),
            )
            if not git.commit_contains_regular_file(
                repository_root,
                target_commit,
                relative_blend_path,
            ):
                raise RuntimeError(
                    f"'{relative_blend_path.as_posix()}' does not exist as a regular file "
                    f"in commit {target_commit[:8]}."
                )
        except Exception as exc:
            message = str(exc)
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            return {"CANCELLED"}

        preferences = get_addon_preferences(context)
        if preferences.create_backup_before_checkout:
            try:
                backup = create_timestamped_backup(
                    blend_path,
                    checkout_backup_directory(
                        repository_root,
                        bpy.utils.user_resource("CONFIG"),
                    ),
                )
                append_output(context, f"Backup created outside the repository: {backup}", "SUCCESS")
            except Exception as exc:
                self.report({"ERROR"}, f"Backup failed: {exc}")
                return {"CANCELLED"}

        try:
            reload_token = _begin_commit_reload(
                blend_path,
                repository_root,
                target_commit,
            )
            git.checkout_commit(repository_root, target_commit)
            if git.head_branch(repository_root):
                raise RuntimeError("Git did not enter detached HEAD.")
            if git.head_commit(repository_root) != target_commit:
                raise RuntimeError("Git HEAD does not match the selected commit.")
            if repository_has_checkout_changes(git, repository_root):
                raise RuntimeError("The checkout left uncommitted repository changes.")
            validate_blend_file_for_reload(blend_path)
        except Exception as exc:
            if "reload_token" not in locals():
                message = str(exc)
                self.report({"ERROR"}, message)
                append_output(context, message, "ERROR")
                return {"CANCELLED"}
            restored, recovery = _restore_source_after_reload_failure(
                git,
                repository_root,
                blend_path,
                source_branch,
                source_commit,
                target_commit,
                cleanup_paths,
            )
            message = f"Could not load commit {target_commit[:8]}: {exc} {recovery}"
            if not restored:
                message += " Do not save the current scene over the checked-out file."
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            _clear_pending_commit_reload(reload_token)
            return {"CANCELLED"}

        append_output(
            context,
            f"Checked out commit {target_commit[:8]}; reloading {blend_path.name}.",
            "INFO",
        )
        reloaded, reload_error = _reload_blend_from_commit(
            str(blend_path),
            str(repository_root),
            target_commit,
        )
        if not reloaded:
            restored, recovery = _restore_source_after_reload_failure(
                git,
                repository_root,
                blend_path,
                source_branch,
                source_commit,
                target_commit,
                cleanup_paths,
            )
            message = f"Could not reload commit {target_commit[:8]}: {reload_error} {recovery}"
            if not restored:
                message += " Do not save the current scene over the checked-out file."
            _append_reload_message(message, "ERROR")
            _clear_pending_commit_reload(reload_token)
            return {"CANCELLED"}
        return {"FINISHED"}
