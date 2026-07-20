from __future__ import annotations

import shutil

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty


class BlenderGitManagerPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    git_executable: StringProperty(
        name="Git executable",
        subtype="FILE_PATH",
        default=shutil.which("git") or "git",
    )
    git_lfs_executable: StringProperty(
        name="Git LFS executable",
        subtype="FILE_PATH",
        description="Informational path. Git LFS is invoked through the selected Git executable",
        default=shutil.which("git-lfs") or "git-lfs",
    )
    gh_executable: StringProperty(
        name="GitHub CLI executable",
        subtype="FILE_PATH",
        default=shutil.which("gh") or "gh",
    )
    save_blend_before_commit: BoolProperty(name="Save .blend before commit", default=True)
    create_backup_before_checkout: BoolProperty(name="Create backup before branch or commit checkout", default=True)
    refresh_automatically: BoolProperty(name="Refresh repository automatically", default=False)
    refresh_interval: FloatProperty(name="Refresh interval", default=5.0, min=2.0, max=300.0, subtype="TIME")
    default_remote: StringProperty(name="Default remote", default="origin")
    default_branch: StringProperty(name="Default branch", default="main")
    enable_advanced_operations: BoolProperty(name="Enable advanced Git operations", default=False)
    show_developer_output: BoolProperty(name="Show developer output", default=False)

    def draw(self, _context):
        layout = self.layout
        executables = layout.box()
        executables.label(text="Command line dependencies", icon="CONSOLE")
        executables.prop(self, "git_executable")
        executables.prop(self, "git_lfs_executable")
        executables.prop(self, "gh_executable")

        workflow = layout.box()
        workflow.label(text="Workflow")
        workflow.prop(self, "save_blend_before_commit")
        workflow.prop(self, "create_backup_before_checkout")
        workflow.prop(self, "default_remote")
        workflow.prop(self, "default_branch")
        workflow.prop(self, "refresh_automatically")
        if self.refresh_automatically:
            workflow.prop(self, "refresh_interval")

        advanced = layout.box()
        advanced.label(text="Advanced")
        advanced.prop(self, "enable_advanced_operations")
        advanced.prop(self, "show_developer_output")


def get_addon_preferences(context: bpy.types.Context) -> BlenderGitManagerPreferences:
    addon = context.preferences.addons.get(__package__)
    if addon is None:
        # Legacy installs may expose the package's final component only.
        addon = context.preferences.addons.get(__package__.split(".")[-1])
    if addon is None:
        raise RuntimeError("Blender Git Manager preferences are unavailable.")
    return addon.preferences
