from __future__ import annotations

import bpy
from bpy.props import StringProperty

from ..state_sync import append_output, build_services, refresh_repository_state


class GITMANAGER_OT_lfs_track(bpy.types.Operator):
    bl_idname = "git_manager.lfs_track"
    bl_label = "Track LFS Pattern"

    pattern: StringProperty(name="Pattern", default="*.blend")

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def execute(self, context):
        state = context.scene.git_manager
        _git, lfs, _github, _repository = build_services(context)
        try:
            if not state.lfs_active:
                lfs.initialize_local(state.repository_path)
            lfs.track(state.repository_path, self.pattern)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        append_output(context, f"Git LFS now tracks {self.pattern}. Remember to stage .gitattributes.", "SUCCESS")
        refresh_repository_state(context, include_dependencies=False)
        return {"FINISHED"}


class GITMANAGER_OT_lfs_untrack(bpy.types.Operator):
    bl_idname = "git_manager.lfs_untrack"
    bl_label = "Untrack LFS Pattern"

    pattern: StringProperty(name="Pattern", default="*.blend")

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def execute(self, context):
        state = context.scene.git_manager
        _git, lfs, _github, _repository = build_services(context)
        try:
            lfs.untrack(state.repository_path, self.pattern)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        append_output(context, f"Git LFS no longer tracks {self.pattern}. Stage .gitattributes.", "WARNING")
        refresh_repository_state(context, include_dependencies=False)
        return {"FINISHED"}
