from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, SimpleQueue
from typing import Any, Callable

import bpy

from ..preferences import get_addon_preferences
from ..services.process_service import ProcessService
from ..state_sync import append_output, refresh_repository_state
from ..utils.formatting import redact_text

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="blender-git-manager")


class AsyncModalMixin:
    _future: Future | None = None
    _timer = None
    _process_service: ProcessService | None = None
    _process_output: SimpleQueue[tuple[str, str]] | None = None
    _transient_process_output: SimpleQueue[tuple[str, str]] | None = None
    _cancel_requested = False
    _task_label = ""

    def start_async(
        self,
        context: bpy.types.Context,
        label: str,
        function: Callable[[], Any],
        process: ProcessService | None = None,
        capture_transient_output: bool = False,
    ):
        state = context.scene.git_manager
        if state.task_running:
            self.report({"WARNING"}, f"Another Git task is already running: {state.task_label}")
            return {"CANCELLED"}

        self._task_label = label
        self._cancel_requested = False
        self._process_output = SimpleQueue()
        self._transient_process_output = SimpleQueue() if capture_transient_output else None
        self._process_service = process
        if process is not None:
            process.reset_cancellation()
            process.set_output_callback(self._queue_process_output)
            process.set_transient_output_callback(
                self._queue_transient_process_output if capture_transient_output else None
            )

        state.task_running = True
        state.task_label = label
        append_output(context, f"{label}...", "INFO")
        self._future = _EXECUTOR.submit(function)
        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _queue_process_output(self, level: str, message: str) -> None:
        queue = self._process_output
        if queue is not None:
            queue.put((level, message))

    def _queue_transient_process_output(self, stream: str, message: str) -> None:
        queue = self._transient_process_output
        if queue is not None:
            queue.put((stream, message))

    def _drain_process_output(self, context: bpy.types.Context) -> None:
        transient_queue = self._transient_process_output
        if transient_queue is not None:
            while True:
                try:
                    stream, message = transient_queue.get_nowait()
                except Empty:
                    break
                self.on_transient_process_output(context, stream, message)

        queue = self._process_output
        if queue is None:
            return
        while True:
            try:
                level, message = queue.get_nowait()
            except Empty:
                break
            self.on_process_output(context, level, message)

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == "ESC":
            if not self._cancel_requested:
                self._cancel_requested = True
                context.scene.git_manager.task_label = f"Cancelling {self._task_label}"
                append_output(context, f"Cancelling {self._task_label}...", "WARNING")
                self.report({"WARNING"}, f"Cancelling {self._task_label}...")
                if self._process_service is not None:
                    self._process_service.cancel()
                elif self._future is not None:
                    self._future.cancel()
            return {"RUNNING_MODAL"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        self._drain_process_output(context)
        if self._future is None or not self._future.done():
            return {"PASS_THROUGH"}

        outcome = {"FINISHED"}
        try:
            result = self._future.result()
            if self._cancel_requested:
                self.on_async_cancel(context)
                append_output(context, f"{self._task_label} cancelled.", "WARNING")
                outcome = {"CANCELLED"}
            else:
                self.on_async_success(context, result)
                append_output(context, f"{self._task_label} completed.", "SUCCESS")
        except Exception as exc:
            if self._cancel_requested:
                self.on_async_cancel(context)
                append_output(context, f"{self._task_label} cancelled.", "WARNING")
                outcome = {"CANCELLED"}
            else:
                message = redact_text(str(exc))
                append_output(context, message, "ERROR")
                self.report({"ERROR"}, message)
                self.on_async_error(context, exc)
        finally:
            self._finish_timer(context)
        if not self._cancel_requested:
            refresh_repository_state(context, include_dependencies=False)
        return outcome

    def _finish_timer(self, context: bpy.types.Context) -> None:
        self._drain_process_output(context)
        if self._process_service is not None:
            self._process_service.set_output_callback(None)
            self._process_service.set_transient_output_callback(None)
            self._process_service = None
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.scene.git_manager.task_running = False
        context.scene.git_manager.task_label = ""
        self._future = None
        self._process_output = None
        self._transient_process_output = None

    def on_async_success(self, _context: bpy.types.Context, _result: Any) -> None:
        pass

    def on_async_error(self, _context: bpy.types.Context, _error: Exception) -> None:
        pass

    def on_async_cancel(self, _context: bpy.types.Context) -> None:
        pass

    def on_process_output(self, context: bpy.types.Context, level: str, message: str) -> None:
        if message.startswith("[command]"):
            try:
                if not get_addon_preferences(context).show_developer_output:
                    return
            except RuntimeError:
                return
        append_output(context, message, level, echo_console=False)

    def on_transient_process_output(self, _context: bpy.types.Context, _stream: str, _message: str) -> None:
        pass
