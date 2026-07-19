from __future__ import annotations

from pathlib import Path

import bpy
from bpy.props import BoolProperty, StringProperty

from ..preferences import get_addon_preferences
from ..state_sync import append_output, build_services, refresh_repository_state
from ..utils.backups import create_timestamped_backup


class GITMANAGER_OT_create_branch(bpy.types.Operator):
    bl_idname = "git_manager.create_branch"
    bl_label = "Create Branch"

    branch_name: StringProperty(name="Branch name")
    switch_to_branch: BoolProperty(name="Switch to new branch", default=True)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def execute(self, context):
        state = context.scene.git_manager
        git, _lfs, _github, _repository = build_services(context)
        try:
            git.create_branch(state.repository_path, self.branch_name, self.switch_to_branch)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        refresh_repository_state(context, include_dependencies=False)
        append_output(context, f"Branch created: {self.branch_name}", "SUCCESS")
        return {"FINISHED"}


class GITMANAGER_OT_switch_branch(bpy.types.Operator):
    bl_idname = "git_manager.switch_branch"
    bl_label = "Switch Branch"

    branch_name: StringProperty()

    def execute(self, context):
        state = context.scene.git_manager
        if state.blend_unsaved:
            self.report({"ERROR"}, "Save or commit Blender changes before switching branches.")
            return {"CANCELLED"}
        preferences = get_addon_preferences(context)
        if preferences.create_backup_before_checkout and bpy.data.filepath:
            try:
                backup = create_timestamped_backup(bpy.data.filepath)
                append_output(context, f"Backup created: {backup}", "SUCCESS")
            except Exception as exc:
                self.report({"ERROR"}, f"Backup failed: {exc}")
                return {"CANCELLED"}
        git, _lfs, _github, _repository = build_services(context)
        try:
            git.switch_branch(state.repository_path, self.branch_name)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        refresh_repository_state(context, include_dependencies=False)
        append_output(context, f"Switched to {self.branch_name}.", "SUCCESS")
        return {"FINISHED"}
