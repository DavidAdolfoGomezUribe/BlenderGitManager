from __future__ import annotations

import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty

from ..state_sync import append_output, build_services, refresh_repository_state
from ..utils.blend_files import validate_blend_file_for_reload
from ..utils.paths import is_path_inside
from .base import AsyncModalMixin, reject_if_task_running

_RELOAD_CALLBACKS: set[object] = set()


def _github_repository_url(remote_url: str) -> str:
    value = remote_url.strip()
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
    else:
        parsed = urlsplit(value)
        if parsed.hostname is None or parsed.hostname.casefold() != "github.com":
            raise ValueError("The configured remote is not hosted on GitHub.")
        path = parsed.path
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if len([part for part in path.split("/") if part]) < 2:
        raise ValueError("The configured GitHub remote URL is incomplete.")
    return f"https://github.com/{path}"


def _schedule_reverted_scene_reload(filepath: str, repository_path: str) -> None:
    def reload_scene():
        try:
            expected = Path(filepath).expanduser().resolve(strict=False)
            current = (
                Path(bpy.data.filepath).expanduser().resolve(strict=False)
                if bpy.data.filepath
                else None
            )
            if current != expected:
                raise RuntimeError("The active Blender file changed before revert reload.")
            if bpy.data.is_dirty:
                raise RuntimeError(
                    "The Blender scene became dirty before revert reload; save it under "
                    "another name before inspecting the reverted file."
                )
            validate_blend_file_for_reload(expected)
            result = bpy.ops.wm.open_mainfile(
                filepath=str(expected),
                load_ui=False,
                use_scripts=False,
                display_file_selector=False,
            )
            if "FINISHED" not in result:
                raise RuntimeError("Blender cancelled the reverted scene reload.")
            bpy.context.scene.git_manager.repository_path = repository_path
            refresh_repository_state(bpy.context, include_dependencies=False)
            append_output(
                bpy.context,
                f"Reloaded {expected.name} after reverting the commit.",
                "SUCCESS",
            )
        except Exception as exc:
            try:
                append_output(
                    bpy.context,
                    (
                        f"The Git revert was created, but Blender could not reload the "
                        f"scene: {exc} Do not overwrite the reverted file with a stale scene."
                    ),
                    "ERROR",
                )
            except Exception:
                print(
                    "[Blender Git Manager][ERROR] "
                    f"Revert scene reload failed: {exc}",
                    flush=True,
                )
        finally:
            _RELOAD_CALLBACKS.discard(reload_scene)
        return None

    _RELOAD_CALLBACKS.add(reload_scene)
    bpy.app.timers.register(reload_scene, first_interval=0.15)


class GITMANAGER_OT_copy_commit_hash(bpy.types.Operator):
    bl_idname = "git_manager.copy_commit_hash"
    bl_label = "Copy Commit Hash"
    bl_description = "Copy the full selected commit hash to the clipboard"

    commit_hash: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        git, _lfs, _github, _repository = build_services(context)
        try:
            object_id = git.resolve_commit(
                context.scene.git_manager.repository_path,
                self.commit_hash,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        context.window_manager.clipboard = object_id
        self.report({"INFO"}, f"Copied commit {object_id[:8]}.")
        return {"FINISHED"}


class GITMANAGER_OT_create_branch_from_commit(bpy.types.Operator):
    bl_idname = "git_manager.create_branch_from_commit"
    bl_label = "Create Branch from Commit"
    bl_description = "Create a local branch whose tip is the selected exact commit"

    commit_hash: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    branch_name: StringProperty(name="Branch name")
    switch_to_branch: BoolProperty(name="Switch and reload scene", default=True)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=460)

    def execute(self, context):
        if reject_if_task_running(self, context):
            return {"CANCELLED"}
        state = context.scene.git_manager
        git, _lfs, _github, _repository = build_services(context)
        try:
            object_id = git.resolve_commit(state.repository_path, self.commit_hash)
            git.create_branch_at(
                state.repository_path,
                self.branch_name,
                object_id,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            append_output(context, str(exc), "ERROR")
            return {"CANCELLED"}

        refresh_repository_state(context, include_dependencies=False)
        append_output(
            context,
            f"Created branch '{self.branch_name.strip()}' at {object_id[:8]}.",
            "SUCCESS",
        )
        if self.switch_to_branch:
            result = bpy.ops.git_manager.switch_branch(
                "EXEC_DEFAULT",
                branch_name=self.branch_name.strip(),
            )
            if "FINISHED" not in result:
                self.report(
                    {"WARNING"},
                    "The branch was created, but Blender could not switch to it.",
                )
                return {"CANCELLED"}
        return {"FINISHED"}


class GITMANAGER_OT_create_tag_from_commit(bpy.types.Operator):
    bl_idname = "git_manager.create_tag_from_commit"
    bl_label = "Create Tag"
    bl_description = "Create a lightweight or annotated tag on the selected exact commit"

    commit_hash: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    tag_name: StringProperty(name="Tag name")
    message: StringProperty(
        name="Annotation",
        description="Leave empty to create a lightweight tag",
    )

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=460)

    def execute(self, context):
        if reject_if_task_running(self, context):
            return {"CANCELLED"}
        state = context.scene.git_manager
        git, _lfs, _github, _repository = build_services(context)
        try:
            object_id = git.resolve_commit(state.repository_path, self.commit_hash)
            git.create_tag_at(
                state.repository_path,
                self.tag_name,
                object_id,
                self.message,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            append_output(context, str(exc), "ERROR")
            return {"CANCELLED"}
        refresh_repository_state(context, include_dependencies=False)
        from .history_runtime import schedule_history_refresh

        schedule_history_refresh(context)
        append_output(
            context,
            f"Created tag '{self.tag_name.strip()}' at {object_id[:8]}.",
            "SUCCESS",
        )
        return {"FINISHED"}


class GITMANAGER_OT_open_commit_remote(bpy.types.Operator):
    bl_idname = "git_manager.open_commit_remote"
    bl_label = "Open Commit on GitHub"
    bl_description = "Open the selected commit on the configured GitHub remote"

    commit_hash: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        state = context.scene.git_manager
        git, _lfs, _github, _repository = build_services(context)
        try:
            object_id = git.resolve_commit(state.repository_path, self.commit_hash)
            repository_url = _github_repository_url(state.remote_url)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        url = f"{repository_url}/commit/{object_id}"
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            context.window_manager.clipboard = url
            self.report(
                {"WARNING"},
                "The browser could not be opened; the commit URL was copied.",
            )
        else:
            self.report({"INFO"}, "Commit opened in the default browser.")
        return {"FINISHED"}


class GITMANAGER_OT_revert_commit(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.revert_commit"
    bl_label = "Confirm Revert Commit"
    bl_description = "Create a new commit that reverses the selected commit"
    _cancel_supported = False

    commit_hash: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    mainline: IntProperty(
        name="Merge mainline parent",
        description="Parent number treated as the mainline when reverting a merge",
        default=1,
        min=1,
        max=16,
    )
    confirm_revert: BoolProperty(
        name="I understand this creates a new reverting commit",
        default=False,
    )

    def draw(self, _context):
        layout = self.layout
        warning = layout.box()
        warning.alert = True
        warning.label(text=f"Revert commit {self.commit_hash[:8]}?", icon="ERROR")
        warning.label(text="The repository must be clean and attached to a branch.")
        layout.prop(self, "mainline")
        layout.prop(self, "confirm_revert")

    def invoke(self, context, _event):
        self.confirm_revert = False
        return context.window_manager.invoke_props_dialog(self, width=520)

    def execute(self, context):
        if not self.confirm_revert:
            self.report({"ERROR"}, "Confirm the revert before continuing.")
            return {"CANCELLED"}
        if reject_if_task_running(self, context):
            return {"CANCELLED"}
        if bpy.data.is_dirty or not bpy.data.filepath:
            self.report({"ERROR"}, "Save the Blender file before reverting a commit.")
            return {"CANCELLED"}

        state = context.scene.git_manager
        git, _lfs, _github, _repository = build_services(context)
        root = git.detect_root(state.repository_path)
        blend_path = Path(bpy.data.filepath).expanduser().resolve(strict=False)
        if root is None or not is_path_inside(blend_path, root):
            self.report({"ERROR"}, "The current Blender file must be inside the repository.")
            return {"CANCELLED"}
        try:
            object_id = git.resolve_commit(root, self.commit_hash)
            if not git.head_branch(root):
                raise RuntimeError(
                    "Switch to or create a branch before reverting a commit."
                )
            if git.repository_has_changes(root):
                raise RuntimeError(
                    "Commit or discard every repository change before reverting."
                )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        relative_blend_path = blend_path.relative_to(root).as_posix()
        repository_path = str(root)
        mainline = int(self.mainline)

        def worker():
            details = git.commit_details(root, object_id, mainline=mainline)
            touches_blend = any(
                file.path == relative_blend_path
                or file.old_path == relative_blend_path
                for file in details.files
            )
            result = git.revert_commit(root, object_id, mainline=mainline)
            return result, touches_blend

        return self.start_async(
            context,
            f"Revert commit {object_id[:8]}",
            worker,
            process=git.process,
        )

    def on_async_success(self, context, result):
        command_result, touches_blend = result
        append_output(
            context,
            command_result.stdout or "Revert commit created.",
            "SUCCESS",
        )
        refresh_repository_state(context, include_dependencies=False)
        if touches_blend:
            _schedule_reverted_scene_reload(
                bpy.data.filepath,
                context.scene.git_manager.repository_path,
            )


def cancel_history_action_callbacks() -> None:
    for callback in tuple(_RELOAD_CALLBACKS):
        try:
            if bpy.app.timers.is_registered(callback):
                bpy.app.timers.unregister(callback)
        except (AttributeError, RuntimeError):
            pass
    _RELOAD_CALLBACKS.clear()


CLASSES = (
    GITMANAGER_OT_copy_commit_hash,
    GITMANAGER_OT_create_branch_from_commit,
    GITMANAGER_OT_create_tag_from_commit,
    GITMANAGER_OT_open_commit_remote,
    GITMANAGER_OT_revert_commit,
)
