from __future__ import annotations

import bpy


class GITMANAGER_MT_git(bpy.types.Menu):
    bl_idname = "GITMANAGER_MT_git"
    bl_label = "Git"

    def draw(self, context):
        layout = self.layout
        state = context.scene.git_manager
        layout.operator("git_manager.open_manager", icon="WINDOW")
        layout.separator()
        repository_actions = layout.column(align=True)
        repository_actions.enabled = not bool(state.repository_path)
        repository_actions.operator("git_manager.initialize_repository", icon="ADD")
        repository_actions.operator("git_manager.open_repository", icon="FILE_FOLDER")
        repository_actions.operator("git_manager.clone_repository", icon="IMPORT")
        layout.separator()
        layout.operator("git_manager.quick_save", text="Quick Save", icon="FILE_TICK")
        layout.separator()
        if state.github_authenticated:
            layout.operator("git_manager.github_logout", text="Disconnect GitHub", icon="UNLINKED")
        else:
            layout.operator("git_manager.github_login", text="GitHub Authentication", icon="URL")
        layout.operator("git_manager.open_preferences", text="Settings", icon="PREFERENCES")


def draw_git_menu(self, _context):
    self.layout.menu(GITMANAGER_MT_git.bl_idname)
