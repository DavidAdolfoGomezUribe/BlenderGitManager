from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.utils.formatting import redact_arguments


class ProcessServiceTests(unittest.TestCase):
    def test_process_output(self):
        result = ProcessService(echo_console=False).run(sys.executable, ["-c", "print('ok')"], timeout=10)
        self.assertTrue(result.successful)
        self.assertEqual(result.stdout, "ok")

    def test_process_failure(self):
        result = ProcessService(echo_console=False).run(
            sys.executable,
            ["-c", "import sys; sys.exit(7)"],
            timeout=10,
        )
        self.assertEqual(result.return_code, 7)
        self.assertFalse(result.successful)

    def test_uses_popen_with_safe_universal_settings_and_environment(self):
        variable = "BGM_PROCESS_SERVICE_TEST"
        environment = {variable: "environment-ok"}
        script = (
            "import os; "
            f"print(os.environ[{variable!r}]); "
            "print('path-inherited=' + str(bool(os.environ.get('PATH'))))"
        )

        with patch(
            "blender_git_manager.services.process_service.subprocess.Popen",
            wraps=subprocess.Popen,
        ) as popen:
            result = ProcessService(echo_console=False).run(
                sys.executable,
                ["-c", script],
                timeout=10,
                environment=environment,
            )

        self.assertTrue(result.successful, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["environment-ok", "path-inherited=True"])
        popen.assert_called_once()
        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(command, [sys.executable, "-c", script])
        self.assertIs(options["shell"], False)
        self.assertIs(options["text"], True)
        self.assertEqual(options["encoding"].lower().replace("-", ""), "utf8")
        self.assertEqual(options["errors"], "replace")
        self.assertEqual(options["env"][variable], "environment-ok")
        self.assertEqual(options["env"].get("PATH"), os.environ.get("PATH"))

    def test_streams_stdout_and_stderr_before_process_finishes(self):
        events: list[tuple[str, str]] = []
        stdout_seen = threading.Event()
        result_box = {}

        def output_callback(level: str, message: str) -> None:
            events.append((level, message))
            if message.startswith("[stdout]") and "ready-before-exit" in message:
                stdout_seen.set()

        service = ProcessService(default_timeout=10, output_callback=output_callback, echo_console=False)
        script = (
            "import sys, time; "
            "print('ready-before-exit', flush=True); "
            "time.sleep(0.5); "
            "print('stderr-after-delay', file=sys.stderr, flush=True)"
        )

        def run_process() -> None:
            result_box["result"] = service.run(sys.executable, ["-c", script])

        worker = threading.Thread(target=run_process, daemon=True)
        worker.start()
        self.assertTrue(stdout_seen.wait(5), "stdout was not delivered incrementally")
        self.assertTrue(worker.is_alive(), "callback was delivered only after the process exited")
        worker.join(10)
        self.assertFalse(worker.is_alive(), "process runner did not finish")

        result = result_box["result"]
        self.assertTrue(result.successful, result.stderr)
        self.assertEqual(result.stdout, "ready-before-exit")
        self.assertEqual(result.stderr, "stderr-after-delay")
        messages = [message for _level, message in events]
        self.assertTrue(any(message.startswith("[command]") for message in messages))
        self.assertTrue(any(message.startswith("[stdout]") and "ready-before-exit" in message for message in messages))
        self.assertTrue(any(message.startswith("[stderr]") and "stderr-after-delay" in message for message in messages))
        self.assertTrue(any(message.startswith("[process]") for message in messages))

    def test_large_stdout_and_stderr_do_not_deadlock(self):
        line_count = 512
        script = (
            "import sys; "
            f"[print(f'out-{{i}}-' + 'x' * 256) for i in range({line_count})]; "
            f"[print(f'err-{{i}}-' + 'y' * 256, file=sys.stderr) for i in range({line_count})]"
        )

        result = ProcessService(default_timeout=10, echo_console=False).run(sys.executable, ["-c", script])

        self.assertTrue(result.successful, result.stderr[-500:])
        stdout_lines = result.stdout.splitlines()
        stderr_lines = result.stderr.splitlines()
        self.assertEqual(len(stdout_lines), line_count)
        self.assertEqual(len(stderr_lines), line_count)
        self.assertTrue(stdout_lines[0].startswith("out-0-"))
        self.assertTrue(stdout_lines[-1].startswith(f"out-{line_count - 1}-"))
        self.assertTrue(stderr_lines[0].startswith("err-0-"))
        self.assertTrue(stderr_lines[-1].startswith(f"err-{line_count - 1}-"))

    def test_callback_failure_does_not_break_process(self):
        callback_calls = 0

        def failing_callback(_level: str, _message: str) -> None:
            nonlocal callback_calls
            callback_calls += 1
            raise RuntimeError("test callback failure")

        result = ProcessService(output_callback=failing_callback, echo_console=False).run(
            sys.executable,
            ["-c", "print('process-survived')"],
            timeout=10,
        )

        self.assertTrue(result.successful, result.stderr)
        self.assertEqual(result.stdout, "process-survived")
        self.assertGreaterEqual(callback_calls, 3)

    def test_default_timeout_returns_standard_timeout_result(self):
        service = ProcessService(default_timeout=0.2, echo_console=False)
        result = service.run(sys.executable, ["-c", "import time; time.sleep(30)"])

        self.assertEqual(result.return_code, 124)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.cancelled)
        self.assertFalse(result.successful)

    def test_cancel_stops_active_process_and_reset_allows_another_run(self):
        ready = threading.Event()
        result_box = {}

        def output_callback(_level: str, message: str) -> None:
            if message.startswith("[stdout]") and "ready-to-cancel" in message:
                ready.set()

        service = ProcessService(default_timeout=30, output_callback=output_callback, echo_console=False)

        def run_process() -> None:
            result_box["result"] = service.run(
                sys.executable,
                ["-c", "import time; print('ready-to-cancel', flush=True); time.sleep(30)"],
            )

        worker = threading.Thread(target=run_process, daemon=True)
        worker.start()
        self.assertTrue(ready.wait(5), "child process never became ready for cancellation")
        service.cancel()
        worker.join(10)
        self.assertFalse(worker.is_alive(), "cancel() left the active process running")

        cancelled = result_box["result"]
        self.assertEqual(cancelled.return_code, 130)
        self.assertTrue(cancelled.cancelled)
        self.assertFalse(cancelled.timed_out)
        self.assertFalse(cancelled.successful)

        service.reset_cancellation()
        follow_up = service.run(sys.executable, ["-c", "print('after-reset')"], timeout=10)
        self.assertTrue(follow_up.successful, follow_up.stderr)
        self.assertEqual(follow_up.stdout, "after-reset")

    @unittest.skipUnless(os.name == "nt", "Windows process-tree cancellation test")
    def test_cancel_stops_descendant_processes_on_windows(self):
        ready = threading.Event()
        result_box = {}
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "descendant-survived.txt"
            child = (
                "import pathlib,time; "
                "time.sleep(1.5); "
                f"pathlib.Path({str(marker)!r}).write_text('survived')"
            )
            parent = (
                "import subprocess,sys,time; "
                f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
                "print('tree-ready', flush=True); "
                "time.sleep(30)"
            )

            def output_callback(_level: str, message: str) -> None:
                if "tree-ready" in message:
                    ready.set()

            service = ProcessService(
                default_timeout=30,
                output_callback=output_callback,
                echo_console=False,
            )

            def run_process() -> None:
                result_box["result"] = service.run(
                    sys.executable,
                    ["-c", parent],
                )

            worker = threading.Thread(target=run_process, daemon=True)
            worker.start()
            self.assertTrue(ready.wait(5), "process tree never became ready")
            service.cancel()
            worker.join(10)
            self.assertFalse(worker.is_alive())
            time.sleep(1.8)
            self.assertFalse(marker.exists(), "cancel() left a descendant process running")
            self.assertTrue(result_box["result"].cancelled)

    def test_output_callback_receives_only_redacted_process_text(self):
        events: list[tuple[str, str]] = []
        secret = "ghp_BGM_TEST_SENTINEL_123456789"
        service = ProcessService(
            output_callback=lambda level, message: events.append((level, message)),
            echo_console=False,
        )
        result = service.run(
            sys.executable,
            ["-c", "import os; print(os.environ['BGM_SECRET_OUTPUT'])"],
            timeout=10,
            environment={"BGM_SECRET_OUTPUT": f"Authorization: Bearer {secret}"},
        )

        self.assertTrue(result.successful, result.stderr)
        emitted = "\n".join(message for _level, message in events)
        self.assertNotIn(secret, emitted)
        self.assertIn("***", emitted)

    def test_transient_callback_receives_raw_code_while_logs_stay_redacted(self):
        code = "ABCD-EFGH"
        raw_events: list[tuple[str, str]] = []
        output_events: list[tuple[str, str]] = []
        console_output = io.StringIO()
        message = f"! One-time code ({code}) copied to clipboard"
        service = ProcessService(
            output_callback=lambda level, text: output_events.append((level, text)),
            transient_output_callback=lambda stream, text: raw_events.append((stream, text)),
            echo_console=True,
        )

        with redirect_stdout(console_output):
            result = service.run(
                sys.executable,
                ["-c", "import os, sys; print(os.environ['BGM_DEVICE_MESSAGE'], file=sys.stderr)"],
                timeout=10,
                environment={"BGM_DEVICE_MESSAGE": message},
            )

        self.assertTrue(result.successful, result.stderr)
        self.assertIn(("stderr", message), raw_events)

        persisted_output = "\n".join(text for _level, text in output_events)
        self.assertNotIn(code, persisted_output)
        self.assertIn("***-****", persisted_output)

        console = console_output.getvalue()
        self.assertNotIn(code, console)
        self.assertIn("***-****", console)

    def test_transient_callback_failure_does_not_break_or_leak_process_output(self):
        code = "WXYZ-1234"
        callback_calls = 0
        output_events: list[tuple[str, str]] = []

        def failing_callback(_stream: str, raw_message: str) -> None:
            nonlocal callback_calls
            callback_calls += 1
            raise RuntimeError(f"callback rejected {raw_message}")

        service = ProcessService(
            output_callback=lambda level, text: output_events.append((level, text)),
            transient_output_callback=failing_callback,
            echo_console=False,
        )
        result = service.run(
            sys.executable,
            ["-c", "import os; print(os.environ['BGM_DEVICE_MESSAGE'])"],
            timeout=10,
            environment={"BGM_DEVICE_MESSAGE": f"One-time code: {code}"},
        )

        self.assertTrue(result.successful, result.stderr)
        self.assertEqual(callback_calls, 1)
        persisted_output = "\n".join(text for _level, text in output_events)
        self.assertIn("Transient output callback failed", persisted_output)
        self.assertNotIn(code, persisted_output)
        self.assertIn("***-****", persisted_output)

    def test_transient_callback_can_be_cleared_before_a_later_run(self):
        raw_events: list[tuple[str, str]] = []
        service = ProcessService(
            transient_output_callback=lambda stream, text: raw_events.append((stream, text)),
            echo_console=False,
        )

        first = service.run(sys.executable, ["-c", "print('first-transient-line')"], timeout=10)
        service.set_transient_output_callback(None)
        second = service.run(sys.executable, ["-c", "print('second-private-line')"], timeout=10)

        self.assertTrue(first.successful, first.stderr)
        self.assertTrue(second.successful, second.stderr)
        self.assertEqual(raw_events, [("stdout", "first-transient-line")])

    def test_echo_console_false_keeps_console_quiet(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = ProcessService(echo_console=False).run(
                sys.executable,
                ["-c", "print('captured-child-output')"],
                timeout=10,
            )

        self.assertTrue(result.successful, result.stderr)
        self.assertEqual(output.getvalue(), "")

    def test_echo_console_true_prints_sanitized_lifecycle(self):
        output = io.StringIO()
        secret = "ghp_BGM_CONSOLE_SENTINEL_123456789"
        with redirect_stdout(output):
            result = ProcessService(echo_console=True).run(
                sys.executable,
                ["-c", "import os; print(os.environ['BGM_CONSOLE_OUTPUT'])"],
                timeout=10,
                environment={"BGM_CONSOLE_OUTPUT": f"Authorization: Bearer {secret}"},
            )

        self.assertTrue(result.successful, result.stderr)
        console = output.getvalue()
        self.assertIn("[Blender Git Manager]", console)
        self.assertIn("[command]", console)
        self.assertIn("[stdout]", console)
        self.assertIn("[process]", console)
        self.assertNotIn(secret, console)
        self.assertIn("***", console)

    def test_redaction(self):
        args = redact_arguments(["--token", "abc", "https://user:secret@github.com/owner/repo.git"])
        self.assertEqual(args[1], "***")
        self.assertNotIn("secret", args[2])
