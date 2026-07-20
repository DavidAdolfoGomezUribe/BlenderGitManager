"""Safe central process execution service.

Every external command is passed as an argument list with shell=False. This module
has no dependency on Blender and is unit-testable.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import TextIO

from ..models import CommandResult
from ..utils.formatting import redact_arguments, redact_text

ProcessOutputCallback = Callable[[str, str], None]
ProcessTransientOutputCallback = Callable[[str, str], None]
_CONSOLE_LOCK = Lock()


def _write_console(message: str) -> None:
    try:
        with _CONSOLE_LOCK:
            print(message, flush=True)
    except (AttributeError, OSError, UnicodeError, ValueError):
        pass


class ProcessService:
    def __init__(
        self,
        default_timeout: int = 120,
        output_callback: ProcessOutputCallback | None = None,
        echo_console: bool = True,
        transient_output_callback: ProcessTransientOutputCallback | None = None,
    ) -> None:
        self.default_timeout = default_timeout
        self._output_callback = output_callback
        self._transient_output_callback = transient_output_callback
        self._echo_console = echo_console
        self._callback_lock = Lock()
        self._process_lock = Lock()
        self._active_process: subprocess.Popen[str] | None = None
        self._cancel_requested = Event()

    def set_output_callback(self, callback: ProcessOutputCallback | None) -> None:
        with self._callback_lock:
            self._output_callback = callback

    def set_transient_output_callback(self, callback: ProcessTransientOutputCallback | None) -> None:
        """Set an in-memory raw-output sink that must never write its values to logs."""
        with self._callback_lock:
            self._transient_output_callback = callback

    def emit_status(self, level: str, message: str) -> None:
        """Publish a sanitized service status through the normal console/output channel."""
        self._emit(level, message)

    def wait_for_retry(self, delay_seconds: float) -> bool:
        """Wait without blocking cancellation; return false when cancellation was requested."""
        return not self._cancel_requested.wait(max(0.0, float(delay_seconds)))

    def reset_cancellation(self) -> None:
        self._cancel_requested.clear()

    def cancel(self) -> None:
        self._cancel_requested.set()
        self._emit("WARNING", "[process] Cancellation requested.")
        with self._process_lock:
            process = self._active_process
        if process is not None and process.poll() is None:
            self._stop_process(process)

    def _emit(self, level: str, message: str) -> None:
        safe_message = redact_text(message).strip()
        if not safe_message:
            return

        if self._echo_console:
            timestamp = datetime.now().strftime("%H:%M:%S")
            _write_console(f"[Blender Git Manager][{timestamp}][{level}] {safe_message}")

        with self._callback_lock:
            callback = self._output_callback
        if callback is not None:
            try:
                callback(level, safe_message)
            except Exception as exc:  # noqa: BLE001 - logging must never break a command
                if self._echo_console:
                    _write_console(
                        f"[Blender Git Manager][WARNING] Process output callback failed: {redact_text(str(exc))}"
                    )

    def _emit_transient(self, stream: str, message: str) -> None:
        with self._callback_lock:
            callback = self._transient_output_callback
        if callback is not None:
            try:
                callback(stream, message)
            except Exception:  # noqa: BLE001 - never expose raw output through an error
                self._emit("WARNING", "[process] Transient output callback failed.")

    @staticmethod
    def _format_command(command: Sequence[str]) -> str:
        safe_command = redact_arguments(command)
        if os.name == "nt":
            return subprocess.list2cmdline(safe_command)
        return shlex.join(safe_command)

    def _read_stream(self, stream: TextIO, chunks: list[str], label: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                chunks.append(line)
                message = line.rstrip("\r\n")
                if message:
                    self._emit_transient(label, message)
                    self._emit("INFO", f"[{label}] {message}")
        except (OSError, ValueError) as exc:
            if not self._cancel_requested.is_set():
                self._emit("WARNING", f"[process] Could not read {label}: {exc}")
        finally:
            try:
                stream.close()
            except OSError:
                pass

    @staticmethod
    def _terminate_windows_descendants(root_pid: int) -> None:
        """Terminate descendants from a Toolhelp snapshot without invoking a shell."""
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessEntry32W(ctypes.Structure):
                _fields_ = (
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260),
                )

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_snapshot = kernel32.CreateToolhelp32Snapshot
            create_snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
            create_snapshot.restype = wintypes.HANDLE
            process_first = kernel32.Process32FirstW
            process_first.argtypes = (
                wintypes.HANDLE,
                ctypes.POINTER(ProcessEntry32W),
            )
            process_first.restype = wintypes.BOOL
            process_next = kernel32.Process32NextW
            process_next.argtypes = (
                wintypes.HANDLE,
                ctypes.POINTER(ProcessEntry32W),
            )
            process_next.restype = wintypes.BOOL
            open_process = kernel32.OpenProcess
            open_process.argtypes = (
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            )
            open_process.restype = wintypes.HANDLE
            terminate_process = kernel32.TerminateProcess
            terminate_process.argtypes = (wintypes.HANDLE, wintypes.UINT)
            terminate_process.restype = wintypes.BOOL
            wait_for_single = kernel32.WaitForSingleObject
            wait_for_single.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            wait_for_single.restype = wintypes.DWORD
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = (wintypes.HANDLE,)
            close_handle.restype = wintypes.BOOL

            snapshot = create_snapshot(0x00000002, 0)
            invalid_handle = ctypes.c_void_p(-1).value
            if not snapshot or snapshot == invalid_handle:
                return
            children: dict[int, list[int]] = {}
            try:
                entry = ProcessEntry32W()
                entry.dwSize = ctypes.sizeof(ProcessEntry32W)
                has_entry = bool(process_first(snapshot, ctypes.byref(entry)))
                while has_entry:
                    parent = int(entry.th32ParentProcessID)
                    children.setdefault(parent, []).append(
                        int(entry.th32ProcessID)
                    )
                    has_entry = bool(process_next(snapshot, ctypes.byref(entry)))
            finally:
                close_handle(snapshot)

            descendants: list[int] = []
            pending = list(children.get(int(root_pid), ()))
            while pending:
                process_id = pending.pop()
                descendants.append(process_id)
                pending.extend(children.get(process_id, ()))

            process_access = 0x0001 | 0x00100000
            for process_id in reversed(descendants):
                handle = open_process(process_access, False, process_id)
                if not handle:
                    continue
                try:
                    terminate_process(handle, 130)
                    wait_for_single(handle, 1000)
                finally:
                    close_handle(handle)
        except (AttributeError, OSError, TypeError, ValueError):
            # The normal parent-process termination below remains available.
            return

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            ProcessService._terminate_windows_descendants(process.pid)
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def run(
        self,
        executable: str,
        arguments: Sequence[str],
        working_directory: str | Path | None = None,
        timeout: int | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if not executable or "\x00" in executable:
            raise ValueError("Executable path is invalid.")
        safe_arguments = [str(argument) for argument in arguments]
        if any("\x00" in argument for argument in safe_arguments):
            raise ValueError("Command argument contains a null character.")

        command = [executable, *safe_arguments]
        cwd = str(Path(working_directory).expanduser().resolve()) if working_directory else None
        env = os.environ.copy()
        if environment:
            env.update({str(key): str(value) for key, value in environment.items()})
        env.setdefault("NO_COLOR", "1")

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW

        started = time.perf_counter()
        effective_timeout = timeout if timeout is not None else self.default_timeout
        self._emit("INFO", f"[command] {self._format_command(command)}")
        if self._cancel_requested.is_set():
            self._emit("WARNING", "[process] Command skipped because cancellation was requested.")
            return CommandResult(
                executable=executable,
                arguments=tuple(safe_arguments),
                return_code=130,
                stderr="Command cancelled.",
                duration_seconds=time.perf_counter() - started,
                cancelled=True,
            )
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                env=env,
                startupinfo=startupinfo,
                creationflags=creationflags,
                bufsize=1,
            )
        except OSError as exc:
            duration = time.perf_counter() - started
            self._emit("ERROR", f"[process] Could not start command: {exc}")
            return CommandResult(
                executable=executable,
                arguments=tuple(safe_arguments),
                return_code=127,
                stderr=str(exc),
                duration_seconds=duration,
            )

        with self._process_lock:
            self._active_process = process
            cancel_immediately = self._cancel_requested.is_set()
        if cancel_immediately:
            self._stop_process(process)

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        readers: list[Thread] = []
        if process.stdout is not None:
            readers.append(
                Thread(
                    target=self._read_stream,
                    args=(process.stdout, stdout_chunks, "stdout"),
                    name="bgm-stdout",
                    daemon=True,
                )
            )
        if process.stderr is not None:
            readers.append(
                Thread(
                    target=self._read_stream,
                    args=(process.stderr, stderr_chunks, "stderr"),
                    name="bgm-stderr",
                    daemon=True,
                )
            )
        for reader in readers:
            reader.start()

        timed_out = False
        try:
            process.wait(timeout=effective_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._stop_process(process)
        finally:
            with self._process_lock:
                if self._active_process is process:
                    self._active_process = None

        for reader in readers:
            reader.join(timeout=2)
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass

        duration = time.perf_counter() - started
        stdout = "".join(stdout_chunks).rstrip("\r\n")
        stderr = "".join(stderr_chunks).rstrip("\r\n")
        cancelled = self._cancel_requested.is_set() and not timed_out

        if timed_out:
            return_code = 124
            stderr = stderr or "Command timed out."
            self._emit("ERROR", f"[process] Timed out after {duration:.2f}s.")
        elif cancelled:
            return_code = 130
            stderr = stderr or "Command cancelled."
            self._emit("WARNING", f"[process] Cancelled after {duration:.2f}s.")
        else:
            return_code = process.returncode if process.returncode is not None else 1
            level = "INFO" if return_code == 0 else "ERROR"
            self._emit(level, f"[process] Exit code {return_code} after {duration:.2f}s.")

        return CommandResult(
            executable=executable,
            arguments=tuple(safe_arguments),
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            timed_out=timed_out,
            cancelled=cancelled,
        )
