from __future__ import annotations

import math
import os
import time

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty


_GESTURE_TOKEN = 0
_ACTIVE_GESTURE = None
_SCHEDULED_CHECKOUTS: set[tuple[str, str, int]] = set()
_SCHEDULED_CALLBACKS: set[object] = set()
_MAX_POINTER_DISTANCE_PX = 12.0


def _repository_key(repository_path: str) -> str:
    if not repository_path:
        return ""
    return os.path.normcase(os.path.abspath(os.path.normpath(repository_path)))


def _validate_target(context, repository: str, commit_hash: str, commit_index: int) -> tuple[bool, str]:
    scene = getattr(context, "scene", None)
    state = getattr(scene, "git_manager", None)
    if state is None:
        return False, "Git Manager state is unavailable."
    if not repository or _repository_key(state.repository_path) != repository:
        return False, "The active repository changed; select the commit again."
    if not commit_hash or commit_index < 0 or commit_index >= len(state.commits):
        return False, "The selected commit is no longer available."
    if state.commits[commit_index].full_hash != commit_hash:
        return False, "Commit history changed; select the commit again."
    return True, ""


def _next_gesture_token() -> int:
    global _GESTURE_TOKEN
    _GESTURE_TOKEN += 1
    return _GESTURE_TOKEN


def _replace_active_gesture(context) -> int:
    """Invalidate and synchronously remove any older row-click timer."""
    global _ACTIVE_GESTURE
    previous = _ACTIVE_GESTURE
    _ACTIVE_GESTURE = None
    if previous is not None:
        try:
            previous._finish_wait(context)
        except (AttributeError, ReferenceError, RuntimeError):
            pass
    return _next_gesture_token()


class GITMANAGER_OT_history_commit_click(bpy.types.Operator):
    """Select a history row and recognize a deliberate double-click."""

    bl_idname = "git_manager.history_commit_click"
    bl_label = "Select History Commit"
    bl_description = "Select this commit; double-click it to load its files and Blender scene"
    bl_options = {"INTERNAL"}

    commit_hash: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    commit_index: IntProperty(default=-1, options={"HIDDEN", "SKIP_SAVE"})
    load_immediately: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})

    _timer = None
    _token = 0
    _repository = ""
    _started_at = 0.0
    _deadline = 0.0
    _mouse_x = 0
    _mouse_y = 0

    @classmethod
    def description(cls, _context, properties):
        if properties.load_immediately:
            return "Load the selected commit's files and reopen the current Blender scene"
        return cls.bl_description

    def _select_target(self, context) -> tuple[bool, str]:
        state = getattr(getattr(context, "scene", None), "git_manager", None)
        if state is None:
            return False, "Git Manager state is unavailable."
        repository = _repository_key(state.repository_path)
        valid, message = _validate_target(context, repository, self.commit_hash, self.commit_index)
        if not valid:
            return False, message
        state.commits_index = self.commit_index
        self._repository = repository
        return True, ""

    def _finish_wait(self, context) -> None:
        global _ACTIVE_GESTURE
        if self._timer is not None:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except (ReferenceError, RuntimeError):
                pass
            self._timer = None
        if _ACTIVE_GESTURE is self:
            _ACTIVE_GESTURE = None

    def _schedule_checkout(self, context):
        valid, message = _validate_target(
            context,
            self._repository,
            self.commit_hash,
            self.commit_index,
        )
        if not valid:
            self.report({"WARNING"}, message)
            return {"CANCELLED"}

        state = context.scene.git_manager
        if state.task_running:
            self.report({"WARNING"}, f"Another Git task is already running: {state.task_label}")
            return {"CANCELLED"}

        checkout_key = (self._repository, self.commit_hash, self.commit_index)
        if checkout_key in _SCHEDULED_CHECKOUTS:
            return {"FINISHED"}
        _SCHEDULED_CHECKOUTS.add(checkout_key)

        repository = self._repository
        commit_hash = self.commit_hash
        commit_index = self.commit_index
        gesture_token = self._token

        def run_checkout():
            try:
                if gesture_token != _GESTURE_TOKEN:
                    return None
                current_context = bpy.context
                valid_now, reason = _validate_target(
                    current_context,
                    repository,
                    commit_hash,
                    commit_index,
                )
                if not valid_now:
                    print(f"[Blender Git Manager] Commit checkout cancelled: {reason}")
                    return None
                current_state = current_context.scene.git_manager
                if current_state.task_running:
                    print(
                        "[Blender Git Manager] Commit checkout cancelled: "
                        f"another task is running ({current_state.task_label})."
                    )
                    return None
                bpy.ops.git_manager.checkout_commit(
                    "EXEC_DEFAULT",
                    commit_hash=commit_hash,
                    commit_index=commit_index,
                )
            except (AttributeError, ReferenceError, RuntimeError) as exc:
                print(f"[Blender Git Manager] Could not start commit checkout: {exc}")
            finally:
                _SCHEDULED_CHECKOUTS.discard(checkout_key)
                _SCHEDULED_CALLBACKS.discard(run_checkout)
            return None

        try:
            _SCHEDULED_CALLBACKS.add(run_checkout)
            bpy.app.timers.register(run_checkout, first_interval=0.0)
        except (AttributeError, RuntimeError) as exc:
            _SCHEDULED_CHECKOUTS.discard(checkout_key)
            _SCHEDULED_CALLBACKS.discard(run_checkout)
            self.report({"ERROR"}, f"Could not schedule commit checkout: {exc}")
            return {"CANCELLED"}
        return {"FINISHED"}

    def invoke(self, context, event):
        global _ACTIVE_GESTURE

        self._token = _replace_active_gesture(context)
        valid, message = self._select_target(context)
        if not valid:
            self.report({"WARNING"}, message)
            return {"CANCELLED"}

        if self.load_immediately:
            return self._schedule_checkout(context)

        self._mouse_x = int(getattr(event, "mouse_x", 0))
        self._mouse_y = int(getattr(event, "mouse_y", 0))
        self._started_at = time.monotonic()
        double_click_ms = float(
            getattr(getattr(context.preferences, "inputs", None), "mouse_double_click_time", 350)
        )
        self._deadline = self._started_at + max(0.1, min(2.0, double_click_ms / 1000.0))

        # Some Blender UI configurations dispatch the completed gesture directly
        # to invoke instead of sending it to the modal handler.
        if event.type == "LEFTMOUSE" and event.value == "DOUBLE_CLICK":
            return self._schedule_checkout(context)

        if context.window is None:
            self.report({"WARNING"}, "Double-click detection requires an active Blender window.")
            return {"CANCELLED"}

        self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
        _ACTIVE_GESTURE = self
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        self._token = _replace_active_gesture(context)
        # A regular row executed without invoke must remain selection-only.
        if not self.load_immediately:
            valid, message = self._select_target(context)
            if not valid:
                self.report({"WARNING"}, message)
                return {"CANCELLED"}
            return {"FINISHED"}
        valid, message = self._select_target(context)
        if not valid:
            self.report({"WARNING"}, message)
            return {"CANCELLED"}
        return self._schedule_checkout(context)

    def modal(self, context, event):
        if self._token != _GESTURE_TOKEN:
            self._finish_wait(context)
            return {"CANCELLED"}

        valid, _message = _validate_target(
            context,
            self._repository,
            self.commit_hash,
            self.commit_index,
        )
        if not valid:
            self._finish_wait(context)
            return {"CANCELLED"}

        now = time.monotonic()
        if event.type == "ESC":
            self._finish_wait(context)
            return {"CANCELLED"}
        if now > self._deadline:
            self._finish_wait(context)
            return {"FINISHED"}

        if event.type == "LEFTMOUSE" and event.value == "DOUBLE_CLICK":
            distance = math.hypot(
                int(getattr(event, "mouse_x", 0)) - self._mouse_x,
                int(getattr(event, "mouse_y", 0)) - self._mouse_y,
            )
            if distance <= _MAX_POINTER_DISTANCE_PX:
                self._finish_wait(context)
                return self._schedule_checkout(context)

        return {"PASS_THROUGH"}


def cancel_history_interaction() -> None:
    global _ACTIVE_GESTURE
    _next_gesture_token()
    active = _ACTIVE_GESTURE
    _ACTIVE_GESTURE = None
    if active is not None:
        try:
            active._finish_wait(bpy.context)
        except (AttributeError, ReferenceError, RuntimeError):
            pass
    for callback in tuple(_SCHEDULED_CALLBACKS):
        try:
            if bpy.app.timers.is_registered(callback):
                bpy.app.timers.unregister(callback)
        except (AttributeError, RuntimeError):
            pass
    _SCHEDULED_CALLBACKS.clear()
    _SCHEDULED_CHECKOUTS.clear()
