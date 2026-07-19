from __future__ import annotations

import io
import os
import sys
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.utils.formatting import redact_arguments


class ProcessServiceTests(unittest.TestCase):
    def test_process_output(self):
        result = ProcessService().run(sys.executable, ["-c", "print('ok')"], timeout=10)
        self.assertTrue(result.successful)
        self.assertEqual(result.stdout, "ok")

    def test_process_failure(self):
        result = ProcessService().run(sys.executable, ["-c", "import sys; sys.exit(7)"], timeout=10)
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
            wraps=__import__("subprocess").Popen,
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

    def test_redaction(self):
        args = redact_arguments(["--token", "abc", "https://user:secret@github.com/owner/repo.git"])
        self.assertEqual(args[1], "***")
        self.assertNotIn("secret", args[2])
