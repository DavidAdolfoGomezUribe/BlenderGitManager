from __future__ import annotations

import bpy
from bpy.props import EnumProperty

from ..preferences import get_addon_preferences
from ..state_sync import append_output, build_services
from .base import AsyncModalMixin


class GITMANAGER_OT_synchronize(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.synchronize"
    bl_label = "Synchronize Repository"

    operation: EnumProperty(
        items=(
            ("FETCH", "Fetch", "Download remote references"),
            ("PULL", "Pull", "Fast-forward the current branch"),
            ("PUSH", "Push", "Upload local commits"),
            ("SYNC", "Sync", "Fetch, pull and push"),
        ),
        default="FETCH",
    )

    def execute(self, context):
        state = context.scene.git_manager
        if not state.repository_path:
            self.report({"ERROR"}, "Open a repository first.")
            return {"CANCELLED"}
        git, _lfs, _github, _repository = build_services(context)
        remote = get_addon_preferences(context).default_remote

        def worker():
            if self.operation == "FETCH":
                return git.fetch(state.repository_path, remote)
            if self.operation == "PULL":
                return git.pull(state.repository_path)
            if self.operation == "PUSH":
                try:
                    return git.push(state.repository_path, remote)
                except Exception:
                    return git.push(state.repository_path, remote, state.active_branch, set_upstream=True)
            return git.sync(state.repository_path, remote)

        return self.start_async(context, self.operation.title(), worker, process=git.process)

    def on_async_success(self, context, result):
        append_output(context, result.stdout or result.stderr or f"{self.operation.title()} completed.", "SUCCESS")
