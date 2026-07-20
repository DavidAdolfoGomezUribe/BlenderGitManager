from __future__ import annotations

import bpy
from bpy.props import BoolProperty

from ..preferences import get_addon_preferences
from ..services.git_service import GitCommandError
from ..state_sync import append_output, build_services, refresh_repository_state
from .base import AsyncModalMixin, reject_if_task_running


class GITMANAGER_OT_commit(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.commit"
    bl_label = "Commit"

    push_after: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        state = getattr(getattr(context, "scene", None), "git_manager", None)
        if state is not None and state.active_branch == "Detached HEAD":
            cls.poll_message_set(
                "Switch to a branch or create one from this commit before committing."
            )
            return False
        return True

    def execute(self, context):
        state = context.scene.git_manager
        if reject_if_task_running(self, context):
            return {"CANCELLED"}
        if not state.repository_path:
            self.report({"ERROR"}, "Open or initialize a repository first.")
            return {"CANCELLED"}
        if not state.commit_message.strip():
            self.report({"ERROR"}, "Commit message cannot be empty.")
            return {"CANCELLED"}

        git, _lfs, _github, _repository = build_services(context)
        repository_root = git.detect_root(state.repository_path)
        if repository_root is None:
            self.report({"ERROR"}, "The selected folder is not an initialized Git repository.")
            return {"CANCELLED"}
        try:
            active_branch = git.head_branch(repository_root)
        except Exception as exc:
            message = f"Could not determine the active Git branch: {exc}"
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            return {"CANCELLED"}
        if not active_branch:
            message = (
                "Commits are disabled in detached HEAD. Switch to a branch or create a new "
                "branch from this commit first."
            )
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            return {"CANCELLED"}

        preferences = get_addon_preferences(context)
        if state.save_before_commit and preferences.save_blend_before_commit:
            if not bpy.data.filepath:
                self.report({"ERROR"}, "Save the Blender file before committing.")
                return {"CANCELLED"}
            try:
                bpy.ops.wm.save_mainfile()
                append_output(context, "Blender file saved before commit.", "SUCCESS")
            except Exception as exc:
                self.report({"ERROR"}, f"Could not save Blender file: {exc}")
                return {"CANCELLED"}

        staged = git.staged_files(repository_root)
        if not staged:
            self.report({"ERROR"}, "There are no staged files.")
            return {"CANCELLED"}

        message = state.commit_message
        description = state.commit_description
        remote = preferences.default_remote
        repository_path = str(repository_root)
        push_after = bool(self.push_after)

        def worker():
            commit_result = git.commit(repository_path, message, description)
            if push_after:
                try:
                    git.push_current(repository_path, remote)
                except Exception as exc:
                    raise GitCommandError(
                        f"Commit '{message}' was created locally, but push failed: {exc}",
                        getattr(exc, "stderr", ""),
                        getattr(exc, "attempts", ()),
                    ) from exc
            return commit_result

        return self.start_async(
            context,
            "Commit and push" if self.push_after else "Create commit",
            worker,
            process=git.process,
        )

    def on_async_success(self, context, result):
        state = context.scene.git_manager
        state.commit_message = ""
        state.commit_description = ""
        append_output(context, result.stdout or "Commit created.", "SUCCESS")
        refresh_repository_state(context, include_dependencies=False)


class GITMANAGER_OT_quick_save(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.quick_save"
    bl_label = "Quick Save"
    bl_description = (
        "Save the Blender file, stage all repository changes, create an incremental "
        "Quick Save commit, and push the active branch"
    )

    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        state = getattr(scene, "git_manager", None)
        if state is None or not state.repository_path:
            cls.poll_message_set("You must initialize a repository before using Quick Save.")
            return False
        if state.task_running:
            cls.poll_message_set(f"Wait for the current Git task to finish: {state.task_label}")
            return False
        if state.active_branch == "Detached HEAD":
            cls.poll_message_set(
                "Switch to a branch or create one from this commit before using Quick Save."
            )
            return False
        return True

    def execute(self, context):
        state = context.scene.git_manager
        if reject_if_task_running(self, context):
            return {"CANCELLED"}

        git, _lfs, _github, _repository = build_services(context)
        root = git.detect_root(state.repository_path)
        if root is None:
            self.report({"ERROR"}, "The selected folder is not an initialized Git repository.")
            return {"CANCELLED"}
        try:
            active_branch = git.head_branch(root)
        except Exception as exc:
            message = f"Could not determine the active Git branch: {exc}"
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            return {"CANCELLED"}
        if not active_branch:
            message = (
                "Quick Save is disabled in detached HEAD. Switch to a branch or create a new "
                "branch from this commit first."
            )
            self.report({"ERROR"}, message)
            append_output(context, message, "ERROR")
            return {"CANCELLED"}

        preferences = get_addon_preferences(context)
        repository_path = str(root)
        remote = str(preferences.default_remote)

        if state.save_before_commit and preferences.save_blend_before_commit:
            if not bpy.data.filepath:
                self.report({"ERROR"}, "Save the Blender file before using Quick Save.")
                return {"CANCELLED"}
            try:
                bpy.ops.wm.save_mainfile()
                append_output(context, "Blender file saved before Quick Save.", "SUCCESS")
            except Exception as exc:
                self.report({"ERROR"}, f"Could not save Blender file: {exc}")
                return {"CANCELLED"}

        def worker():
            return git.quick_save(root, remote)

        return self.start_async(
            context,
            "Quick Save",
            worker,
            process=git.process,
        )

    def on_async_success(self, context, result):
        message = f"{result.message} committed and pushed from branch {result.branch}."
        append_output(context, message, "SUCCESS")
        self.report({"INFO"}, message)
        refresh_repository_state(context, include_dependencies=False)

    def on_async_cancel(self, context):
        message = (
            "Quick Save was cancelled. Check History because the local commit may already "
            "exist if cancellation happened during push."
        )
        append_output(context, message, "WARNING")
        self.report({"WARNING"}, message)
        refresh_repository_state(context, include_dependencies=False)
