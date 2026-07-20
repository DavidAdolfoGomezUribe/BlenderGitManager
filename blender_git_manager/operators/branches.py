from __future__ import annotations

from pathlib import Path

import bpy
from bpy.props import BoolProperty, StringProperty

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
from ..utils.validation import validate_branch_name
from .base import reject_if_task_running

_pending_blend_reload: tuple[str, str, str, str] | None = None
_RELOAD_TASK_LABEL = "Reloading Blender file after branch switch"
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


def is_blend_reload_pending() -> bool:
    return _pending_blend_reload is not None


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


def _clear_pending_blend_reload(token: tuple[str, str, str, str]) -> None:
    global _pending_blend_reload
    if _pending_blend_reload == token:
        _pending_blend_reload = None
        _set_reload_task_state(False)


def cancel_pending_blend_reload() -> None:
    global _pending_blend_reload
    _pending_blend_reload = None
    _set_reload_task_state(False)


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


def _reload_blend_after_branch_switch(
    filepath: str,
    repository_path: str,
    branch_name: str,
    commit_hash: str,
) -> tuple[bool, str]:
    """Reload immediately after checkout without yielding a saveable stale scene to Blender."""
    token = (filepath, repository_path, branch_name, commit_hash)
    if _pending_blend_reload != token:
        return (
            False,
            f"Discarded an outdated Blender reload request for branch '{branch_name}'.",
        )

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
        active_branch = git.head_branch(repository_path)
        if active_branch != branch_name:
            raise RuntimeError(
                f"The active Git branch is '{active_branch or 'unknown'}' instead of "
                f"'{branch_name}'."
            )
        if git.head_commit(repository_path) != commit_hash:
            raise RuntimeError(
                f"Git HEAD changed before Blender could reload branch '{branch_name}'."
            )
        if git.path_has_changes(repository_path, expected_path):
            raise RuntimeError("The Blender file changed on disk before reloading.")
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
        append_output(
            fresh_context,
            f"Switched to {branch_name} and reloaded {expected_path.name}.",
            "SUCCESS",
        )
    except Exception as exc:
        _append_reload_message(
            f"Reloaded {expected_path.name} from branch '{branch_name}', "
            f"but repository status could not be refreshed: {exc}",
            "WARNING",
        )
    finally:
        _clear_pending_blend_reload(token)
    return True, ""


def _begin_blend_reload(
    filepath: Path,
    repository_path: Path,
    branch_name: str,
    commit_hash: str,
) -> tuple[str, str, str, str]:
    global _pending_blend_reload
    path_value = str(filepath)
    repository_value = str(repository_path)
    branch_value = str(branch_name)
    commit_value = str(commit_hash)
    token = (path_value, repository_value, branch_value, commit_value)
    if _pending_blend_reload is not None:
        raise RuntimeError("Another branch file reload is already pending.")
    _pending_blend_reload = token
    _set_reload_task_state(True)
    return token


def _restore_source_branch_after_reload_failure(
    git,
    repository_path: Path,
    blend_path: Path,
    source_branch: str,
    source_commit: str,
    target_branch: str,
    target_commit: str,
    cleanup_paths: tuple[str, ...],
) -> tuple[bool, str]:
    switch_warning = ""
    source_label = f"branch '{source_branch}'" if source_branch else f"detached HEAD {source_commit[:8]}"
    try:
        active_branch = git.head_branch(repository_path)
        active_commit = git.head_commit(repository_path)
        already_at_source = active_branch == source_branch and active_commit == source_commit
        at_target = active_branch == target_branch and active_commit == target_commit
        if at_target and not already_at_source:
            try:
                if source_branch:
                    git.switch_branch(repository_path, source_branch)
                else:
                    git.checkout_commit(repository_path, source_commit)
            except Exception as exc:
                switch_warning = f" Git reported during rollback: {exc}"
                current_branch = git.head_branch(repository_path)
                current_commit = git.head_commit(repository_path)
                if current_branch == target_branch and current_commit == target_commit:
                    git.restore_tree_from_commit(repository_path, source_commit)
                    remove_checkout_created_paths(repository_path, cleanup_paths)
                    try:
                        if source_branch:
                            git.switch_branch(repository_path, source_branch)
                        else:
                            git.checkout_commit(repository_path, source_commit)
                    except Exception as retry_exc:
                        switch_warning += f" | {retry_exc}"
        elif not already_at_source:
            raise RuntimeError(
                f"automatic rollback expected branch '{target_branch}' at {target_commit[:8]} "
                f"or {source_label}, but Git is on "
                f"'{active_branch or 'detached HEAD'}' at {active_commit[:8]}"
            )

        active_branch = git.head_branch(repository_path)
        active_commit = git.head_commit(repository_path)
        if active_branch != source_branch or active_commit != source_commit:
            raise RuntimeError(
                f"Git remained on '{active_branch or 'detached HEAD'}' at "
                f"{active_commit[:8]} instead of {source_label}"
            )
        if repository_has_checkout_changes(git, repository_path):
            git.restore_tree_from_commit(repository_path, source_commit)
        remove_checkout_created_paths(repository_path, cleanup_paths)
        if repository_has_checkout_changes(git, repository_path):
            raise RuntimeError(
                "repository files are still modified after whole-tree rollback"
            )
        validate_blend_file_for_reload(blend_path)
        _refresh_after_failed_reload(str(repository_path), blend_path)
    except Exception as exc:
        return False, f"Automatic rollback to {source_label} failed: {exc}.{switch_warning}"
    if source_branch == target_branch and source_commit == target_commit:
        return True, f"Repository remained on {source_label}.{switch_warning}"
    return True, f"Restored {source_label} after the failure.{switch_warning}"


class GITMANAGER_OT_create_branch(bpy.types.Operator):
    bl_idname = "git_manager.create_branch"
    bl_label = "Create Branch"

    branch_name: StringProperty(name="Branch name")
    switch_to_branch: BoolProperty(name="Switch to new branch", default=True)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def execute(self, context):
        state = context.scene.git_manager
        if reject_if_task_running(self, context):
            return {"CANCELLED"}
        git, _lfs, _github, _repository = build_services(context)
        requested_branch = ""
        source_branch = ""
        source_commit = ""
        try:
            requested_branch = validate_branch_name(self.branch_name)
            source_branch = git.head_branch(state.repository_path)
            source_commit = git.head_commit(state.repository_path)
            git.create_branch(
                state.repository_path,
                requested_branch,
                self.switch_to_branch,
            )
        except Exception as exc:
            if (
                self.switch_to_branch
                and requested_branch
                and requested_branch != source_branch
                and source_commit
            ):
                try:
                    actual_branch = git.head_branch(state.repository_path)
                    actual_commit = git.head_commit(state.repository_path)
                except Exception:
                    actual_branch = ""
                    actual_commit = ""
                if actual_branch == requested_branch and actual_commit == source_commit:
                    refresh_repository_state(context, include_dependencies=False)
                    message = (
                        f"Branch '{requested_branch}' was created and activated, but a Git "
                        f"checkout hook reported an error: {exc}"
                    )
                    append_output(context, message, "WARNING")
                    self.report({"WARNING"}, message)
                    return {"FINISHED"}
            message = str(exc)
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            return {"CANCELLED"}
        refresh_repository_state(context, include_dependencies=False)
        append_output(context, f"Branch created: {requested_branch}", "SUCCESS")
        return {"FINISHED"}


class GITMANAGER_OT_switch_branch(bpy.types.Operator):
    bl_idname = "git_manager.switch_branch"
    bl_label = "Switch Branch"

    branch_name: StringProperty()

    def execute(self, context):
        state = context.scene.git_manager
        if _pending_blend_reload is not None:
            self.report({"WARNING"}, "Wait for the current branch file reload to finish.")
            return {"CANCELLED"}
        if reject_if_task_running(self, context):
            return {"CANCELLED"}
        if bpy.data.is_dirty or not bpy.data.filepath:
            self.report({"ERROR"}, "Save the current Blender file before switching branches.")
            return {"CANCELLED"}
        if not state.repository_path:
            self.report({"ERROR"}, "Open a repository before switching branches.")
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
        branch_name = self.branch_name.strip()
        try:
            source_branch = git.head_branch(repository_root)
            source_commit = git.head_commit(repository_root)
            target_commit = git.branch_head_commit(repository_root, branch_name)
            if repository_has_checkout_changes(git, repository_root):
                raise RuntimeError(
                    "The repository has uncommitted changes. Commit them, create a branch to "
                    "keep them, or discard every change before switching branches."
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
            if git.path_has_changes(repository_root, relative_blend_path):
                raise RuntimeError(
                    f"'{relative_blend_path.as_posix()}' has uncommitted Git changes. "
                    "Commit or discard them before switching branches."
                )
            if not git.branch_contains_regular_file(
                repository_root,
                branch_name,
                relative_blend_path,
            ):
                raise RuntimeError(
                    f"'{relative_blend_path.as_posix()}' does not exist as a regular file "
                    f"in branch '{branch_name}'."
                )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            append_output(context, str(exc), "ERROR")
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
                append_output(
                    context,
                    f"Backup created outside the repository: {backup}",
                    "SUCCESS",
                )
            except Exception as exc:
                self.report({"ERROR"}, f"Backup failed: {exc}")
                return {"CANCELLED"}

        try:
            reload_token = _begin_blend_reload(
                blend_path,
                repository_root,
                branch_name,
                target_commit,
            )
            git.switch_branch(repository_root, branch_name)
            if (
                git.head_branch(repository_root) != branch_name
                or git.head_commit(repository_root) != target_commit
            ):
                raise RuntimeError(
                    f"Git did not switch to branch '{branch_name}' at {target_commit[:8]}."
                )
            if repository_has_checkout_changes(git, repository_root):
                raise RuntimeError(
                    f"Branch '{branch_name}' checkout left uncommitted repository changes."
                )
        except Exception as exc:
            if "reload_token" not in locals():
                self.report({"ERROR"}, str(exc))
                append_output(context, str(exc), "ERROR")
                return {"CANCELLED"}
            restored, recovery = _restore_source_branch_after_reload_failure(
                git,
                repository_root,
                blend_path,
                source_branch,
                source_commit,
                branch_name,
                target_commit,
                cleanup_paths,
            )
            message = f"Could not switch to branch '{branch_name}': {exc} {recovery}"
            if not restored:
                message += " Do not save the current scene over the checked-out file."
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            if _pending_blend_reload == reload_token:
                _clear_pending_blend_reload(reload_token)
            return {"CANCELLED"}
        try:
            validate_blend_file_for_reload(blend_path)
        except Exception as exc:
            restored, recovery = _restore_source_branch_after_reload_failure(
                git,
                repository_root,
                blend_path,
                source_branch,
                source_commit,
                branch_name,
                target_commit,
                cleanup_paths,
            )
            message = f"Could not reload branch '{branch_name}': {exc} {recovery}"
            if not restored:
                message += " Do not save the current scene over the checked-out file."
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            _clear_pending_blend_reload(reload_token)
            return {"CANCELLED"}

        append_output(context, f"Switched to {branch_name}; reloading {blend_path.name}.", "INFO")
        reloaded, reload_error = _reload_blend_after_branch_switch(
            str(blend_path),
            str(repository_root),
            branch_name,
            target_commit,
        )
        if not reloaded:
            restored, recovery = _restore_source_branch_after_reload_failure(
                git,
                repository_root,
                blend_path,
                source_branch,
                source_commit,
                branch_name,
                target_commit,
                cleanup_paths,
            )
            message = f"Could not reload branch '{branch_name}': {reload_error} {recovery}"
            if not restored:
                message += " Do not save the current scene over the checked-out file."
            _append_reload_message(message, "ERROR")
            _clear_pending_blend_reload(reload_token)
            return {"CANCELLED"}
        return {"FINISHED"}
