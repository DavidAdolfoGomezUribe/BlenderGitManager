from __future__ import annotations

import webbrowser

import bpy

from ..services.github_service import find_github_device_login_url
from ..state_sync import append_output, build_services, refresh_dependencies
from .base import AsyncModalMixin


class GITMANAGER_OT_github_login(AsyncModalMixin, bpy.types.Operator):
    bl_idname = "git_manager.github_login"
    bl_label = "Connect to GitHub in Browser"
    bl_description = "Authenticate GitHub CLI with a browser-based flow"
    _browser_opened = False

    def execute(self, context):
        _git, _lfs, github, _repository = build_services(context)
        if not github.version().successful:
            self.report({"ERROR"}, "GitHub CLI is not installed or its path is invalid.")
            return {"CANCELLED"}
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
