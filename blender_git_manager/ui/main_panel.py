from __future__ import annotations

import bpy

from .dashboard import draw_dashboard


class GITMANAGER_PT_main(bpy.types.Panel):
    bl_idname = "GITMANAGER_PT_main"
    bl_label = "Blender Git Manager"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Git"

    def draw(self, context):
        draw_dashboard(self.layout, context, expanded=False)
