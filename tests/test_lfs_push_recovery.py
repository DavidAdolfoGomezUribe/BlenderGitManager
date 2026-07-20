from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, call

from blender_git_manager.models import CommandResult
from blender_git_manager.services.git_service import GitCommandError, GitService
from blender_git_manager.services.lfs_push_failures import (
    LFSFailureKind,
    classify_lfs_push_failure,
    extract_github_locksverify_key,
)
from blender_git_manager.services.process_service import ProcessService


LOCKSVERIFY_KEY = "lfs.https://github.com/octo-org/assets.git/info/lfs.locksverify"
LOCK_WARNING = (
    'Remote "origin" does not support the Git LFS locking API. Consider disabling it with:\n'
    f"  $ git config {LOCKSVERIFY_KEY} false"
)


def command_result(
    *,
    return_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
    cancelled: bool = False,
) -> CommandResult:
    return CommandResult(
        executable="git",
        arguments=("push", "-u", "origin", "feature:refs/heads/feature"),
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        cancelled=cancelled,
    )


class LFSFailureClassifierTests(unittest.TestCase):
    def test_exact_unsupported_lock_warning_with_safe_github_key_is_lock_verify(self):
        result = command_result(
            return_code=1,
            stderr=f"{LOCK_WARNING}\nerror: failed to push some refs",
        )

        self.assertEqual(classify_lfs_push_failure(result), LFSFailureKind.LOCK_VERIFY)
        self.assertEqual(extract_github_locksverify_key(result.stderr), LOCKSVERIFY_KEY)

    def test_lock_classification_requires_both_lock_context_and_safe_key(self):
        cases = {
            "context_without_key": 'Remote "origin" does not support the Git LFS locking API.',
            "key_without_context": f"$ git config {LOCKSVERIFY_KEY} false",
            "non_github_key": (
                'Remote "origin" does not support the Git LFS locking API.\n'
                "$ git config lfs.https://git.example.com/octo/assets.git/info/lfs.locksverify false"
            ),
        }

        for name, stderr in cases.items():
            with self.subTest(name=name):
                result = command_result(return_code=1, stderr=stderr)
                self.assertEqual(classify_lfs_push_failure(result), LFSFailureKind.NONE)

    def test_locksverify_extractor_rejects_unsafe_or_non_github_endpoints(self):
        unsafe_keys = (
            "lfs.http://github.com/octo/assets.git/info/lfs.locksverify",
            "lfs.https://github.example/octo/assets.git/info/lfs.locksverify",
            "lfs.https://github.com.evil.example/octo/assets.git/info/lfs.locksverify",
            "lfs.https://token@github.com/octo/assets.git/info/lfs.locksverify",
            "lfs.https://github.com/octo/assets.git/info/lfs?token=secret.locksverify",
            "lfs.https://github.com/octo/assets.git/info/lfs#fragment.locksverify",
            "lfs.https://github.com/octo/assets.git/locksverify",
        )

        for key in unsafe_keys:
            with self.subTest(key=key):
                self.assertEqual(
                    extract_github_locksverify_key(f"$ git config {key} false"),
                    "",
                )

    def test_locksverify_extractor_rejects_extra_command_tokens(self):
        values = (
            f"$ git config --global {LOCKSVERIFY_KEY} false",
            f"$ git config {LOCKSVERIFY_KEY} true",
            f"$ git config {LOCKSVERIFY_KEY}\n--global false",
            f"$ git config {LOCKSVERIFY_KEY};echo-owned false",
        )

        for value in values:
            with self.subTest(value=value):
                self.assertEqual(extract_github_locksverify_key(value), "")

    def test_batch_http_502_and_remote_timeout_are_transient(self):
        transient_outputs = (
            (
                "batch response: POST "
                "https://github.com/octo/assets.git/info/lfs/objects/batch: HTTP 502 Bad Gateway"
            ),
            (
                "trace git-lfs: HTTP: POST "
                "https://github.com/octo/assets.git/info/lfs/objects/batch\n"
                "batch response: GitHub: We couldn't respond to your request in time"
            ),
            (
                "trace git-lfs: POST "
                "https://github.com/octo/assets.git/info/lfs/objects/batch\n"
                "< HTTP/2.0 502 Bad Gateway"
            ),
            "batch response: upstream returned status code 503",
            "tqclient.Batch: POST objects: i/o timeout",
        )

        for stderr in transient_outputs:
            with self.subTest(stderr=stderr):
                result = command_result(return_code=1, stderr=stderr)
                self.assertEqual(
                    classify_lfs_push_failure(result),
                    LFSFailureKind.TRANSIENT_BATCH,
                )

    def test_transient_marker_without_batch_context_is_not_retried(self):
        result = command_result(
            return_code=1,
            stderr="remote service returned HTTP 502 Bad Gateway",
        )

        self.assertEqual(classify_lfs_push_failure(result), LFSFailureKind.NONE)

    def test_authentication_and_real_lock_failures_are_not_recoverable(self):
        hard_failures = (
            "batch response: Authentication failed: HTTP 502 Bad Gateway",
            "batch response: authorization failed with HTTP 401",
            "batch response: request was forbidden with HTTP/2 403",
            "batch response: authentication required; status code 401",
            (
                f"{LOCK_WARNING}\n"
                "Git credentials for https://github.com/octo-org/assets.git not found."
            ),
            (
                f"{LOCK_WARNING}\n"
                "Unable to push locked files:\n"
                "scene.blend locked by another-user"
            ),
        )

        for stderr in hard_failures:
            with self.subTest(stderr=stderr):
                result = command_result(return_code=1, stderr=stderr)
                self.assertEqual(classify_lfs_push_failure(result), LFSFailureKind.NONE)

    def test_cancelled_or_process_timed_out_results_are_not_retried(self):
        transient = (
            "batch response: POST "
            "https://github.com/octo/assets.git/info/lfs/objects/batch: HTTP 502 Bad Gateway"
        )
        cases = (
            command_result(return_code=130, stderr=transient, cancelled=True),
            command_result(return_code=124, stderr=transient, timed_out=True),
        )

        for result in cases:
            with self.subTest(result=result):
                self.assertEqual(classify_lfs_push_failure(result), LFSFailureKind.NONE)

    def test_success_with_lock_warning_is_not_a_failure(self):
        result = command_result(return_code=0, stderr=LOCK_WARNING)

        self.assertEqual(classify_lfs_push_failure(result), LFSFailureKind.NONE)


class LFSPushRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.process = Mock(spec=ProcessService)
        self.process.wait_for_retry.return_value = True
        self.service = GitService("git", process=self.process)
        self.repository = Path("C:/virtual/lfs-push-repository")
        self.arguments = ["push", "-u", "origin", "feature:refs/heads/feature"]

    def test_combined_attempt_output_preserves_stdout_and_stderr(self):
        attempt = command_result(
            return_code=1,
            stdout="Git push progress",
            stderr="Git LFS failure detail",
        )

        combined = self.service._combined_attempt_output([attempt])

        self.assertIn("[Push attempt 1]", combined)
        self.assertIn("[stdout]\nGit push progress", combined)
        self.assertIn("[stderr]\nGit LFS failure detail", combined)

    def test_lock_verify_failure_uses_ephemeral_override_and_retries_once(self):
        first = command_result(return_code=1, stderr=LOCK_WARNING)
        successful_retry = command_result(stderr="Uploading LFS objects: 100%")
        self.process.run.side_effect = (first, successful_retry)

        result = self.service._push_checked(self.arguments, self.repository)

        self.assertIs(result, successful_retry)
        self.assertEqual(
            self.process.run.call_args_list,
            [
                call("git", self.arguments, self.repository, 1800),
                call(
                    "git",
                    ["-c", f"{LOCKSVERIFY_KEY}=false", *self.arguments],
                    self.repository,
                    1800,
                ),
            ],
        )
        self.process.wait_for_retry.assert_not_called()
        statuses = [args for args, _kwargs in self.process.emit_status.call_args_list]
        self.assertTrue(all(level == "WARNING" for level, _message in statuses))
        self.assertTrue(any("succeeded" in message.lower() for _level, message in statuses))
        self.assertFalse(
            any(process_call.args[1][:2] == ["config", "--local"] for process_call in self.process.run.call_args_list)
        )

    def test_lock_recovery_failure_retries_only_once_and_preserves_push_attempts(self):
        first = command_result(return_code=1, stderr=LOCK_WARNING)
        second = command_result(
            return_code=1,
            stderr="batch response: permanent upload failure",
        )
        self.process.run.side_effect = (first, second)

        with self.assertRaises(GitCommandError) as captured:
            self.service._push_checked(self.arguments, self.repository)

        error = captured.exception
        self.assertEqual(error.attempts, (first, second))
        self.assertIn("[Push attempt 1]", error.stderr)
        self.assertIn(LOCK_WARNING, error.stderr)
        self.assertIn("[Push attempt 2]", error.stderr)
        self.assertIn(second.stderr, error.stderr)
        self.assertEqual(
            self.process.run.call_args_list,
            [
                call("git", self.arguments, self.repository, 1800),
                call(
                    "git",
                    ["-c", f"{LOCKSVERIFY_KEY}=false", *self.arguments],
                    self.repository,
                    1800,
                ),
            ],
        )

    def test_ephemeral_override_does_not_read_or_persist_effective_config(self):
        first = command_result(return_code=1, stderr=LOCK_WARNING)
        successful_retry = command_result(stderr="Uploading LFS objects: 100%")
        self.process.run.side_effect = (first, successful_retry)
        self.service.config_get = Mock(return_value="true")

        result = self.service._push_checked(self.arguments, self.repository)

        self.assertIs(result, successful_retry)
        self.service.config_get.assert_not_called()
        self.assertEqual(
            self.process.run.call_args_list,
            [
                call("git", self.arguments, self.repository, 1800),
                call(
                    "git",
                    ["-c", f"{LOCKSVERIFY_KEY}=false", *self.arguments],
                    self.repository,
                    1800,
                ),
            ],
        )

    def test_transient_batch_failure_waits_and_retries_same_push_once(self):
        first = command_result(
            return_code=1,
            stderr=(
                "batch response: POST "
                "https://github.com/octo/assets.git/info/lfs/objects/batch: HTTP 502 Bad Gateway"
            ),
        )
        successful_retry = command_result(stderr="Uploading LFS objects: 100%")
        self.process.run.side_effect = (first, successful_retry)

        result = self.service._push_checked(self.arguments, self.repository)

        self.assertIs(result, successful_retry)
        self.assertEqual(
            self.process.run.call_args_list,
            [
                call("git", self.arguments, self.repository, 1800),
                call("git", self.arguments, self.repository, 1800),
            ],
        )
        self.process.wait_for_retry.assert_called_once_with(2.0)
        statuses = [args for args, _kwargs in self.process.emit_status.call_args_list]
        self.assertTrue(all(level == "WARNING" for level, _message in statuses))
        self.assertTrue(any("succeeded" in message.lower() for _level, message in statuses))

    def test_transient_batch_final_failure_preserves_both_attempts(self):
        first = command_result(
            return_code=1,
            stderr="batch response: HTTP 502 Bad Gateway",
        )
        second = command_result(
            return_code=1,
            stderr="batch response: service unavailable",
        )
        self.process.run.side_effect = (first, second)

        with self.assertRaises(GitCommandError) as captured:
            self.service._push_checked(self.arguments, self.repository)

        error = captured.exception
        self.assertEqual(error.attempts, (first, second))
        self.assertIn("temporary server error", str(error).lower())
        self.assertIn("[Push attempt 1]", error.stderr)
        self.assertIn(first.stderr, error.stderr)
        self.assertIn("[Push attempt 2]", error.stderr)
        self.assertIn(second.stderr, error.stderr)
        self.assertEqual(self.process.run.call_count, 2)
        self.process.wait_for_retry.assert_called_once_with(2.0)

    def test_lock_then_batch_recovery_keeps_override_for_third_attempt(self):
        first = command_result(return_code=1, stderr=LOCK_WARNING)
        second = command_result(
            return_code=1,
            stderr="batch response: HTTP 502 Bad Gateway",
        )
        third = command_result(stderr="Uploading LFS objects: 100%")
        self.process.run.side_effect = (first, second, third)
        override_arguments = [
            "-c",
            f"{LOCKSVERIFY_KEY}=false",
            *self.arguments,
        ]

        result = self.service._push_checked(self.arguments, self.repository)

        self.assertIs(result, third)
        self.assertEqual(
            self.process.run.call_args_list,
            [
                call("git", self.arguments, self.repository, 1800),
                call("git", override_arguments, self.repository, 1800),
                call("git", override_arguments, self.repository, 1800),
            ],
        )
        self.process.wait_for_retry.assert_called_once_with(2.0)

    def test_batch_then_lock_recovery_applies_override_on_third_attempt(self):
        first = command_result(
            return_code=1,
            stderr="batch response: HTTP 502 Bad Gateway",
        )
        second = command_result(return_code=1, stderr=LOCK_WARNING)
        third = command_result(stderr="Uploading LFS objects: 100%")
        self.process.run.side_effect = (first, second, third)

        result = self.service._push_checked(self.arguments, self.repository)

        self.assertIs(result, third)
        self.assertEqual(
            self.process.run.call_args_list,
            [
                call("git", self.arguments, self.repository, 1800),
                call("git", self.arguments, self.repository, 1800),
                call(
                    "git",
                    ["-c", f"{LOCKSVERIFY_KEY}=false", *self.arguments],
                    self.repository,
                    1800,
                ),
            ],
        )
        self.process.wait_for_retry.assert_called_once_with(2.0)

    def test_cancelled_retry_wait_does_not_launch_another_push(self):
        first = command_result(
            return_code=1,
            stderr="batch response: HTTP 502 Bad Gateway",
        )
        self.process.run.return_value = first
        self.process.wait_for_retry.return_value = False

        with self.assertRaises(GitCommandError) as captured:
            self.service._push_checked(self.arguments, self.repository)

        self.assertEqual(captured.exception.attempts, (first,))
        self.assertNotIn("after the automatic retry", str(captured.exception).lower())
        self.assertEqual(str(captured.exception), first.stderr)
        self.process.run.assert_called_once_with(
            "git",
            self.arguments,
            self.repository,
            1800,
        )
        self.process.wait_for_retry.assert_called_once_with(2.0)

    def test_transient_retry_followed_by_hard_failure_uses_general_message(self):
        first = command_result(
            return_code=1,
            stderr="batch response: HTTP 502 Bad Gateway",
        )
        second = command_result(
            return_code=1,
            stderr="batch response: Authentication failed: HTTP 401",
        )
        self.process.run.side_effect = (first, second)

        with self.assertRaises(GitCommandError) as captured:
            self.service._push_checked(self.arguments, self.repository)

        error = captured.exception
        self.assertEqual(error.attempts, (first, second))
        self.assertIn("recovery attempt", str(error).lower())
        self.assertNotIn("still returning a temporary server error", str(error).lower())
        self.process.wait_for_retry.assert_called_once_with(2.0)

    def test_successful_push_with_lock_warning_is_not_retried_or_configured(self):
        successful = command_result(return_code=0, stderr=LOCK_WARNING)
        self.process.run.return_value = successful

        result = self.service._push_checked(self.arguments, self.repository)

        self.assertIs(result, successful)
        self.process.run.assert_called_once_with(
            "git",
            self.arguments,
            self.repository,
            1800,
        )
        self.process.wait_for_retry.assert_not_called()
        self.process.emit_status.assert_not_called()

    def test_hard_failures_do_not_retry(self):
        hard_failures = (
            command_result(
                return_code=1,
                stderr="batch response: Authentication failed: HTTP 502 Bad Gateway",
            ),
            command_result(
                return_code=1,
                stderr=(
                    f"{LOCK_WARNING}\n"
                    "Unable to push locked files: scene.blend locked by another-user"
                ),
            ),
            command_result(
                return_code=1,
                stderr=(
                    f"{LOCK_WARNING}\n"
                    "Git credentials for https://github.com/octo-org/assets.git not found."
                ),
            ),
            command_result(
                return_code=130,
                stderr="batch response: HTTP 502 Bad Gateway",
                cancelled=True,
            ),
        )

        for failure in hard_failures:
            with self.subTest(stderr=failure.stderr, cancelled=failure.cancelled):
                process = Mock(spec=ProcessService)
                process.run.return_value = failure
                service = GitService("git", process=process)

                with self.assertRaises(GitCommandError) as captured:
                    service._push_checked(self.arguments, self.repository)

                self.assertEqual(captured.exception.attempts, (failure,))
                process.run.assert_called_once_with(
                    "git",
                    self.arguments,
                    self.repository,
                    1800,
                )
                process.wait_for_retry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
