"""Blender Git Manager extension entry point.

The guarded import allows unit tests for service modules to run outside Blender.
"""

from __future__ import annotations

try:
    import bpy  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - only used outside Blender
    bpy = None

_registered = False


def _require_blender():
    if bpy is None:
        raise RuntimeError("Blender Git Manager can only be registered inside Blender.")


def _auto_refresh_timer():
    if not _registered or bpy is None:
        return None
    try:
        from .preferences import get_addon_preferences
        from .state_sync import refresh_repository_state

        context = bpy.context
        preferences = get_addon_preferences(context)
        if preferences.refresh_automatically and context.scene and hasattr(context.scene, "git_manager"):
            if not context.scene.git_manager.task_running:
                refresh_repository_state(context, include_dependencies=False)
        return max(2.0, preferences.refresh_interval)
    except Exception:
        return 10.0


def register() -> None:
    global _registered
    _require_blender()
    from .operators import CLASSES as OPERATOR_CLASSES
    from .preferences import BlenderGitManagerPreferences
    from .properties import register_properties
    from .ui import register_ui

    bpy.utils.register_class(BlenderGitManagerPreferences)
    register_properties()
    for cls in OPERATOR_CLASSES:
        bpy.utils.register_class(cls)
    register_ui()
    _registered = True
    if not bpy.app.timers.is_registered(_auto_refresh_timer):
        bpy.app.timers.register(_auto_refresh_timer, first_interval=3.0, persistent=True)


def unregister() -> None:
    global _registered
    _require_blender()
    from .operators import CLASSES as OPERATOR_CLASSES
    from .operators.branches import cancel_pending_blend_reload
    from .operators.history import cancel_pending_commit_reload
    from .operators.history_actions import cancel_history_action_callbacks
    from .operators.history_runtime import cancel_history_runtime
    from .preferences import BlenderGitManagerPreferences
    from .properties import unregister_properties
    from .ui import unregister_ui

    _registered = False
    cancel_pending_blend_reload()
    cancel_pending_commit_reload()
    cancel_history_action_callbacks()
    cancel_history_runtime()
    if bpy.app.timers.is_registered(_auto_refresh_timer):
        bpy.app.timers.unregister(_auto_refresh_timer)
    unregister_ui()
    for cls in reversed(OPERATOR_CLASSES):
        bpy.utils.unregister_class(cls)
    unregister_properties()
    bpy.utils.unregister_class(BlenderGitManagerPreferences)
