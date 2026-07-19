from __future__ import annotations

import bpy
from bpy.props import BoolProperty

from ..preferences import get_addon_preferences
from ..state_sync import append_output, build_services, refresh_repository_state
from .base import AsyncModalMixin


class GITMANAGER_OT_commit(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.commit"
    bl_label = "Commit"

    push_after: BoolProperty(default=False)

    def execute(self, context):
        state = context.scene.git_manager
        if not state.repository_path:
            self.report({"ERROR"}, "Open or initialize a repository first.")
            return {"CANCELLED"}
        if not state.commit_message.strip():
            self.report({"ERROR"}, "Commit message cannot be empty.")
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

        git, _lfs, _github, _repository = build_services(context)
        staged = git.staged_files(state.repository_path)
        if not staged:
            self.report({"ERROR"}, "There are no staged files.")
            return {"CANCELLED"}

        message = state.commit_message
        description = state.commit_description
        remote = preferences.default_remote
        branch = state.active_branch

        def worker():
            commit_result = git.commit(state.repository_path, message, description)
            if self.push_after:
                try:
                    git.push(state.repository_path, remote)
                except Exception:
                    git.push(state.repository_path, remote, branch, set_upstream=True)
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
