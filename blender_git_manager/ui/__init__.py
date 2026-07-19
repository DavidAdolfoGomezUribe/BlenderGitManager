from __future__ import annotations

import bpy

from .lists import GITMANAGER_UL_branches, GITMANAGER_UL_changes, GITMANAGER_UL_commits, GITMANAGER_UL_output
from .main_panel import GITMANAGER_PT_main
from .top_menu import GITMANAGER_MT_git, draw_git_menu

CLASSES = (
    GITMANAGER_UL_changes,
    GITMANAGER_UL_commits,
    GITMANAGER_UL_branches,
    GITMANAGER_UL_output,
    GITMANAGER_MT_git,
    GITMANAGER_PT_main,
)


def register_ui() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_git_menu)


def unregister_ui() -> None:
    try:
        bpy.types.TOPBAR_MT_editor_menus.remove(draw_git_menu)
    except Exception:
        pass
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
