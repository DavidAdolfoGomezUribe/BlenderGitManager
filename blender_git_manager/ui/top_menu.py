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
        layout.operator("git_manager.initialize_repository", icon="ADD")
        layout.operator("git_manager.open_repository", icon="FILE_FOLDER")
        layout.operator("git_manager.clone_repository", icon="IMPORT")
        layout.separator()
        layout.operator("git_manager.refresh", text="Repository Status", icon="FILE_REFRESH")
        if state.repository_path:
            operator = layout.operator("git_manager.commit", text="Save and Commit", icon="CHECKMARK")
            operator.push_after = False
            for operation, label in (("PULL", "Pull"), ("PUSH", "Push"), ("FETCH", "Fetch")):
                operator = layout.operator("git_manager.synchronize", text=label)
                operator.operation = operation
            layout.operator("git_manager.create_branch", text="Branches", icon="OUTLINER_OB_ARMATURE")
            layout.operator("git_manager.lfs_track", text="Git LFS", icon="PACKAGE")
        layout.separator()
        if state.github_authenticated:
            layout.operator("git_manager.github_logout", text="Disconnect GitHub", icon="UNLINKED")
        else:
            layout.operator("git_manager.github_login", text="GitHub Authentication", icon="URL")
        layout.operator("git_manager.open_preferences", text="Settings", icon="PREFERENCES")


def draw_git_menu(self, _context):
    self.layout.menu(GITMANAGER_MT_git.bl_idname)
