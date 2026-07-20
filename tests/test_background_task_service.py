from __future__ import annotations

import threading
import time
import unittest

from blender_git_manager.services.background_task_service import BackgroundTaskService


class BackgroundTaskServiceTests(unittest.TestCase):
    def test_returns_results_and_errors_without_empty_queue_race(self):
        service = BackgroundTaskService(max_workers=2)
        try:
            success_id = service.submit("success", lambda: 42)
            error_id = service.submit(
                "error",
                lambda: (_ for _ in ()).throw(RuntimeError("failure")),
            )
            completions = self._wait_for(service, 2)
        finally:
            service.shutdown()

        by_id = {completion.task_id: completion for completion in completions}
        self.assertEqual(by_id[success_id].result, 42)
        self.assertIsNone(by_id[success_id].error)
        self.assertIsInstance(by_id[error_id].error, RuntimeError)

    def test_cancel_all_and_shutdown_are_idempotent(self):
        service = BackgroundTaskService(max_workers=1)
        release = threading.Event()
        service.submit("running", lambda: release.wait(1.0))
        service.submit("queued", lambda: "never required")

        service.cancel_all()
        release.set()
        service.shutdown()
        service.shutdown()

        with self.assertRaisesRegex(RuntimeError, "shut down"):
            service.submit("late", lambda: None)

    @staticmethod
    def _wait_for(
        service: BackgroundTaskService,
        expected: int,
        timeout: float = 2.0,
    ):
        deadline = time.monotonic() + timeout
        completions = []
        while len(completions) < expected and time.monotonic() < deadline:
            completions.extend(service.poll())
            if len(completions) < expected:
                time.sleep(0.01)
        if len(completions) != expected:
            raise AssertionError(
                f"Expected {expected} task completion(s), got {len(completions)}"
            )
        return completions


if __name__ == "__main__":
    unittest.main()
