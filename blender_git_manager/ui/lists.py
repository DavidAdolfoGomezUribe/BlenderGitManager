from __future__ import annotations

import bpy


class GITMANAGER_UL_changes(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        status_icon = "ERROR" if item.conflicted else "CHECKMARK" if item.staged else "DOT"
        row.label(text=item.status_code, icon=status_icon)
        row.label(text=item.path)
        if item.uses_lfs:
            row.label(text="LFS", icon="PACKAGE")
        row.label(text=item.size_label)
        if item.staged:
            operator = row.operator("git_manager.unstage", text="", icon="REMOVE")
            operator.path = item.path
        else:
            operator = row.operator("git_manager.stage", text="", icon="ADD")
            operator.path = item.path


class GITMANAGER_UL_commits(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        row.label(text="●")
        row.label(text=item.short_hash)
        row.label(text=item.subject)
        row.label(text=item.author_name, icon="USER")


class GITMANAGER_UL_branches(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        icon = "RADIOBUT_ON" if item.current else "OUTLINER_OB_ARMATURE" if item.remote else "DOT"
        row.label(text=item.name, icon=icon)
        if item.upstream:
            row.label(text=item.upstream)
        row.label(text=item.short_hash)
        if not item.current and not item.remote:
            operator = row.operator("git_manager.switch_branch", text="Switch")
            operator.branch_name = item.name


class GITMANAGER_UL_output(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        icon = {"ERROR": "ERROR", "WARNING": "ERROR", "SUCCESS": "CHECKMARK"}.get(item.level, "INFO")
        row.label(text=item.timestamp)
        row.label(text=item.message, icon=icon)
