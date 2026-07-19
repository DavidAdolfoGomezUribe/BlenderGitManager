from __future__ import annotations

import webbrowser
from pathlib import Path

import bpy

from ..state_sync import append_output, refresh_repository_state


class GITMANAGER_OT_refresh(bpy.types.Operator):
    bl_idname = "git_manager.refresh"
    bl_label = "Refresh Git Manager"
    bl_description = "Refresh dependencies, repository status, history and branches"

    def execute(self, context):
        success = refresh_repository_state(context)
        if success:
            append_output(context, "Repository state refreshed.", "SUCCESS")
        return {"FINISHED"}


class GITMANAGER_OT_open_folder(bpy.types.Operator):
    bl_idname = "git_manager.open_folder"
    bl_label = "Open Repository Folder"

    def execute(self, context):
        path = context.scene.git_manager.repository_path
        if not path or not Path(path).exists():
            self.report({"ERROR"}, "Repository folder is unavailable.")
            return {"CANCELLED"}
        try:
            bpy.ops.wm.path_open(filepath=path)
        except Exception:
            webbrowser.open(Path(path).as_uri())
        return {"FINISHED"}


class GITMANAGER_OT_open_remote(bpy.types.Operator):
    bl_idname = "git_manager.open_remote"
    bl_label = "Open on GitHub"

    def execute(self, context):
        url = context.scene.git_manager.remote_url
        if url.endswith(".git"):
            url = url[:-4]
        if url.startswith("git@github.com:"):
            url = "https://github.com/" + url.split(":", 1)[1]
        if not url.startswith(("https://github.com/", "http://github.com/")):
            self.report({"ERROR"}, "The configured remote is not a recognized GitHub URL.")
            return {"CANCELLED"}
        webbrowser.open(url)
        return {"FINISHED"}

class GITMANAGER_OT_open_preferences(bpy.types.Operator):
    bl_idname = "git_manager.open_preferences"
    bl_label = "Blender Git Manager Settings"

    def execute(self, _context):
        bpy.ops.screen.userpref_show()
        return {"FINISHED"}
