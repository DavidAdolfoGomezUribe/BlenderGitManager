from __future__ import annotations

import webbrowser

import bpy

from ..services.github_service import find_github_device_code, find_github_device_login_url
from ..state_sync import append_output, build_services, refresh_dependencies
from .base import AsyncModalMixin

_ACTIVE_GITHUB_DEVICE_CODE = ""


def _clear_active_device_code() -> None:
    global _ACTIVE_GITHUB_DEVICE_CODE
    _ACTIVE_GITHUB_DEVICE_CODE = ""


def _show_device_code_popup(context) -> bool:
    code = _ACTIVE_GITHUB_DEVICE_CODE
    if not code or context.window is None:
        return False

    def draw(menu, _context):
        layout = menu.layout
        layout.label(text="Enter this temporary code on GitHub:")
        code_row = layout.row()
        code_row.scale_y = 1.5
        code_row.alignment = "CENTER"
        code_row.label(text=code)
        layout.separator()
        layout.label(text="It is also available on the clipboard.")
        layout.operator("git_manager.copy_github_device_code", text="Copy Code Again", icon="COPYDOWN")

    context.window_manager.popup_menu(draw, title="GitHub Device Authentication", icon="INFO")
    return True


class GITMANAGER_OT_copy_github_device_code(bpy.types.Operator):
    bl_idname = "git_manager.copy_github_device_code"
    bl_label = "Copy GitHub Device Code"
    bl_description = "Copy the active temporary GitHub authentication code again"

    @classmethod
    def poll(cls, _context):
        return bool(_ACTIVE_GITHUB_DEVICE_CODE)

    def execute(self, context):
        if not _ACTIVE_GITHUB_DEVICE_CODE:
            self.report({"WARNING"}, "The GitHub device code is no longer active.")
            return {"CANCELLED"}
        context.window_manager.clipboard = _ACTIVE_GITHUB_DEVICE_CODE
        self.report({"INFO"}, "GitHub device code copied to the clipboard.")
        return {"FINISHED"}


class GITMANAGER_OT_show_github_device_code(bpy.types.Operator):
    bl_idname = "git_manager.show_github_device_code"
    bl_label = "Show GitHub Device Code"
    bl_description = "Show the active temporary GitHub authentication code"

    @classmethod
    def poll(cls, _context):
        return bool(_ACTIVE_GITHUB_DEVICE_CODE)

    def execute(self, context):
        if not _show_device_code_popup(context):
            self.report({"WARNING"}, "The GitHub device code is not available yet.")
            return {"CANCELLED"}
        return {"FINISHED"}


class GITMANAGER_OT_github_login(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.github_login"
    bl_label = "Connect to GitHub in Browser"
    bl_description = "Authenticate GitHub CLI with a browser-based flow"
    _browser_opened = False

    def execute(self, context):
        state = context.scene.git_manager
        if state.task_running:
            self.report({"WARNING"}, f"Another Git task is already running: {state.task_label}")
            return {"CANCELLED"}
        _git, _lfs, github, _repository = build_services(context)
        if not github.version().successful:
            self.report({"ERROR"}, "GitHub CLI is not installed or its path is invalid.")
            return {"CANCELLED"}
        _clear_active_device_code()
        self._browser_opened = False
        append_output(
            context,
            "Starting GitHub device authentication. The one-time code will be copied to the clipboard.",
            "INFO",
        )
        return self.start_async(
            context,
            "GitHub browser authentication",
            github.login_web,
            process=github.process,
            capture_transient_output=True,
        )

    def on_transient_process_output(self, context, _stream, message):
        global _ACTIVE_GITHUB_DEVICE_CODE
        code = find_github_device_code(message)
        if not code or code == _ACTIVE_GITHUB_DEVICE_CODE:
            return

        _ACTIVE_GITHUB_DEVICE_CODE = code
        try:
            context.window_manager.clipboard = code
        except Exception:  # noqa: BLE001
            append_output(context, "The device code could not be copied automatically.", "WARNING")
        try:
            _show_device_code_popup(context)
        except Exception:  # noqa: BLE001
            append_output(context, "The device code popup could not be opened.", "WARNING")
        append_output(
            context,
            "The temporary GitHub device code is visible in Blender and can be copied again.",
            "INFO",
        )

    def on_process_output(self, context, level, message):
        super().on_process_output(context, level, message)
        if self._browser_opened or self._cancel_requested:
            return
        url = find_github_device_login_url(message)
        if not url:
            return

        self._browser_opened = True
        try:
            opened = webbrowser.open(url, new=2, autoraise=True)
        except Exception as exc:  # noqa: BLE001
            opened = False
            append_output(context, f"Could not open the browser: {exc}", "ERROR")

        if opened:
            append_output(context, "GitHub authorization opened in the default browser.", "SUCCESS")
            self.report({"INFO"}, "Complete GitHub authorization in the browser, then return to Blender.")
        else:
            append_output(context, f"Open this URL manually to continue: {url}", "WARNING")
            self.report({"WARNING"}, "The browser could not be opened. See Git Output for the device URL.")

    def on_async_success(self, context, _result):
        refresh_dependencies(context)
        state = context.scene.git_manager
        if not state.github_authenticated:
            raise RuntimeError("GitHub CLI finished, but the authenticated session could not be verified.")
        user = state.github_user
        append_output(context, f"Authenticated as {user or 'GitHub user'}.", "SUCCESS")

    def _finish_timer(self, context):
        try:
            super()._finish_timer(context)
        finally:
            _clear_active_device_code()


class GITMANAGER_OT_github_logout(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.github_logout"
    bl_label = "Disconnect GitHub"
    bl_options = {"REGISTER"}

    confirm: bpy.props.BoolProperty(name="Confirm logout", default=False)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, _context):
        self.layout.label(text="This signs GitHub CLI out of the active GitHub account.", icon="ERROR")
        self.layout.prop(self, "confirm")

    def execute(self, context):
        if not self.confirm:
            self.report({"WARNING"}, "Confirm logout first.")
            return {"CANCELLED"}
        _git, _lfs, github, _repository = build_services(context)
        username = context.scene.git_manager.github_user
        return self.start_async(
            context,
            "GitHub logout",
            lambda: github.logout(username),
            process=github.process,
        )

    def on_async_success(self, context, _result):
        refresh_dependencies(context)
        append_output(context, "GitHub CLI session disconnected.", "SUCCESS")
