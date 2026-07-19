from __future__ import annotations

import bpy
from bpy.props import BoolProperty, StringProperty

from ..state_sync import append_output, build_services, refresh_repository_state


def _selected_paths(state, staged: bool | None = None) -> list[str]:
    paths: list[str] = []
    for item in state.changes:
        if not item.selected:
            continue
        if staged is not None and item.staged != staged:
            continue
        paths.append(item.path)
    return paths


class GITMANAGER_OT_stage(bpy.types.Operator):
    bl_idname = "git_manager.stage"
    bl_label = "Stage Files"

    path: StringProperty()
    stage_all: BoolProperty(default=False)

    def execute(self, context):
        state = context.scene.git_manager
        git, _lfs, _github, _repository = build_services(context)
        try:
            if self.stage_all:
                git.add_all(state.repository_path)
            else:
                paths = [self.path] if self.path else _selected_paths(state, staged=False)
                git.add(state.repository_path, paths)
            append_output(context, "Files staged.", "SUCCESS")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            append_output(context, str(exc), "ERROR")
            return {"CANCELLED"}
        refresh_repository_state(context, include_dependencies=False)
        return {"FINISHED"}


class GITMANAGER_OT_unstage(bpy.types.Operator):
    bl_idname = "git_manager.unstage"
    bl_label = "Unstage Files"

    path: StringProperty()
    unstage_all: BoolProperty(default=False)

    def execute(self, context):
        state = context.scene.git_manager
        git, _lfs, _github, _repository = build_services(context)
        try:
            if self.unstage_all:
                git.unstage_all(state.repository_path)
            else:
                paths = [self.path] if self.path else _selected_paths(state, staged=True)
                git.unstage(state.repository_path, paths)
            append_output(context, "Files unstaged.", "SUCCESS")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            append_output(context, str(exc), "ERROR")
            return {"CANCELLED"}
        refresh_repository_state(context, include_dependencies=False)
        return {"FINISHED"}


class GITMANAGER_OT_discard_changes(bpy.types.Operator):
    bl_idname = "git_manager.discard_changes"
    bl_label = "Discard Selected Changes"

    confirm: BoolProperty(name="I understand these changes will be lost", default=False)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, _context):
        self.layout.label(text="This operation cannot be undone by Git.", icon="ERROR")
        self.layout.prop(self, "confirm")

    def execute(self, context):
        if not self.confirm:
            return {"CANCELLED"}
        state = context.scene.git_manager
        paths = _selected_paths(state, staged=False)
        git, _lfs, _github, _repository = build_services(context)
        try:
            git.discard(state.repository_path, paths)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            append_output(context, str(exc), "ERROR")
            return {"CANCELLED"}
        refresh_repository_state(context, include_dependencies=False)
        append_output(context, "Selected changes discarded.", "WARNING")
        return {"FINISHED"}
