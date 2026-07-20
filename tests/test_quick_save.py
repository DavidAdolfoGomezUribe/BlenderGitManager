from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from blender_git_manager.models import CommandResult, RemoteInfo
from blender_git_manager.services.git_service import GitCommandError, GitService
from blender_git_manager.services.process_service import ProcessService


def command_result(
    arguments: tuple[str, ...] = (),
    *,
    return_code: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> CommandResult:
    return CommandResult(
        executable="git",
        arguments=arguments,
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
    )


class QuickSaveNumberTests(unittest.TestCase):
    def setUp(self):
        self.process = Mock(spec=ProcessService)
        self.service = GitService("git", process=self.process)
        self.repository = Path("C:/virtual/quick-save-repository")

    def test_empty_history_starts_at_one(self):
        self.process.run.return_value = command_result(stdout="")

        self.assertEqual(self.service.next_quick_save_number(self.repository), 1)

        self.process.run.assert_called_once()
        positional = self.process.run.call_args.args
        self.assertEqual(positional[0], "git")
        arguments = positional[1]
        self.assertIn("--all", arguments)
        self.assertTrue(any("%s" in argument for argument in arguments))
        self.assertFalse(any("max-count" in argument for argument in arguments))
        self.assertEqual(positional[2], self.repository)

    def test_uses_maximum_exact_positive_quick_save_subject(self):
        self.process.run.return_value = command_result(
            stdout="\n".join(
                (
                    "Quick Save 2",
                    "Unrelated commit",
                    "Quick Save 11",
                    "Quick Save 4",
                    "Quick Save 11",
                    "quick save 99",
                    "Quick Save 0",
                    "Quick Save -8",
                    "Quick Save 0012",
                    "Quick Save 7 extra",
                    "Prefix Quick Save 50",
                    "Quick  Save 80",
                )
            )
        )

        self.assertEqual(self.service.next_quick_save_number(self.repository), 12)

    def test_history_failure_is_not_treated_as_empty_repository(self):
        self.process.run.return_value = command_result(
            return_code=128,
            stderr="fatal: not a git repository",
        )

        with self.assertRaises(GitCommandError):
            self.service.next_quick_save_number(self.repository)


class QuickSaveWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.service = GitService("git", process=Mock(spec=ProcessService))
        self.repository = Path("C:/virtual/quick-save-repository")
        self.root = self.repository.expanduser().resolve(strict=False)

    @staticmethod
    def recording_mock(events: list[str], name: str, value=None) -> Mock:
        def record(*_args, **_kwargs):
            events.append(name)
            return value

        return Mock(side_effect=record)

    def test_stages_then_commits_next_message_and_pushes_current_branch(self):
        events: list[str] = []
        add_result = command_result(("add", "--all"))
        commit_result = command_result(("commit", "-m", "Quick Save 4"), stdout="[feature/materials abc123] Quick Save 4")
        push_result = command_result(("push", "-u", "origin", "feature/materials"), stderr="branch pushed")

        push_plan = self.recording_mock(
            events,
            "push_plan",
            ("feature/materials", "origin", "refs/heads/feature/materials", True),
        )
        status = self.recording_mock(events, "status", [])
        add_all = self.recording_mock(events, "add_all", add_result)
        staged_files = self.recording_mock(events, "staged_files", ["scene.blend"])
        next_number = self.recording_mock(events, "next_number", 4)
        commit = self.recording_mock(events, "commit", commit_result)
        push_current = self.recording_mock(events, "push_current", push_result)

        with (
            patch.object(self.service, "_current_push_plan", push_plan),
            patch.object(self.service, "status", status),
            patch.object(self.service, "add_all", add_all),
            patch.object(self.service, "staged_files", staged_files),
            patch.object(self.service, "next_quick_save_number", next_number),
            patch.object(self.service, "commit", commit),
            patch.object(self.service, "push_current", push_current, create=True),
        ):
            result = self.service.quick_save(self.repository, remote="origin")

        self.assertEqual(result.message, "Quick Save 4")
        self.assertEqual(result.branch, "feature/materials")
        self.assertIs(result.commit, commit_result)
        self.assertIs(result.push, push_result)

        for preflight in ("push_plan", "status"):
            self.assertLess(events.index(preflight), events.index("add_all"))
        self.assertEqual(
            events[events.index("add_all") :],
            ["add_all", "staged_files", "next_number", "commit", "push_current"],
        )

        push_plan.assert_called_once_with(self.root, "origin")
        status.assert_called_once_with(self.root)
        add_all.assert_called_once_with(self.root)
        staged_files.assert_called_once_with(self.root)
        next_number.assert_called_once_with(self.root)
        commit.assert_called_once_with(self.root, "Quick Save 4")
        push_args = push_current.call_args.args
        push_kwargs = push_current.call_args.kwargs
        self.assertEqual(push_args[0], self.root)
        fallback_remote = push_kwargs.get(
            "fallback_remote",
            push_args[1] if len(push_args) > 1 else None,
        )
        self.assertEqual(fallback_remote, "origin")
        self.assertEqual(push_kwargs.get("expected_branch"), "feature/materials")

    def test_no_changes_after_stage_all_does_not_number_commit_or_push(self):
        events: list[str] = []
        push_plan = self.recording_mock(
            events,
            "push_plan",
            ("main", "origin", "refs/heads/main", True),
        )
        status = self.recording_mock(events, "status", [])
        add_all = self.recording_mock(events, "add_all", command_result(("add", "--all")))
        staged_files = self.recording_mock(events, "staged_files", [])
        next_number = self.recording_mock(events, "next_number", 1)
        commit = self.recording_mock(events, "commit", command_result())
        push_current = self.recording_mock(events, "push_current", command_result())

        with (
            patch.object(self.service, "_current_push_plan", push_plan),
            patch.object(self.service, "status", status),
            patch.object(self.service, "add_all", add_all),
            patch.object(self.service, "staged_files", staged_files),
            patch.object(self.service, "next_quick_save_number", next_number),
            patch.object(self.service, "commit", commit),
            patch.object(self.service, "push_current", push_current, create=True),
        ):
            with self.assertRaisesRegex(GitCommandError, r"(?i)(no changes|no staged files)"):
                self.service.quick_save(self.repository)

        self.assertEqual(
            events,
            ["push_plan", "status", "add_all", "staged_files"],
        )
        next_number.assert_not_called()
        commit.assert_not_called()
        push_current.assert_not_called()

    def test_missing_fallback_remote_fails_before_staging(self):
        add_all = Mock()

        with (
            patch.object(self.service, "active_branch", return_value="main"),
            patch.object(self.service, "remotes", return_value=[]),
            patch.object(self.service, "config_get", return_value=""),
            patch.object(self.service, "status", side_effect=AssertionError("status must follow remote preflight")),
            patch.object(self.service, "add_all", add_all),
            patch.object(self.service, "push_current", Mock(), create=True),
        ):
            with self.assertRaisesRegex(GitCommandError, r"(?i)remote"):
                self.service.quick_save(self.repository, remote="origin")

        add_all.assert_not_called()

    def test_existing_upstream_does_not_require_fallback_remote(self):
        commit_result = command_result(("commit", "-m", "Quick Save 3"))
        push_result = command_result(("push",))

        with (
            patch.object(
                self.service,
                "_current_push_plan",
                return_value=("topic", "team", "refs/heads/topic", False),
            ),
            patch.object(self.service, "status", return_value=[]),
            patch.object(self.service, "add_all", return_value=command_result(("add", "--all"))),
            patch.object(self.service, "staged_files", return_value=["scene.blend"]),
            patch.object(self.service, "next_quick_save_number", return_value=3),
            patch.object(self.service, "commit", return_value=commit_result),
            patch.object(self.service, "push_current", return_value=push_result, create=True) as push_current,
        ):
            result = self.service.quick_save(self.repository, remote="missing-origin")

        self.assertEqual(result.message, "Quick Save 3")
        self.assertEqual(result.branch, "topic")
        self.assertIs(result.commit, commit_result)
        self.assertIs(result.push, push_result)
        push_current.assert_called_once()

    def test_push_failure_preserves_all_recovery_attempts(self):
        commit_result = command_result(("commit", "-m", "Quick Save 3"))
        first_attempt = command_result(
            ("push", "-u", "origin", "topic:refs/heads/topic"),
            return_code=1,
            stderr="first Git LFS failure",
        )
        second_attempt = command_result(
            ("-c", "lfs.example=false", "push", "-u", "origin", "topic:refs/heads/topic"),
            return_code=1,
            stderr="second Git LFS failure",
        )
        push_error = GitCommandError(
            "Push failed after recovery.",
            "[Push attempt 1]\nfirst\n\n[Push attempt 2]\nsecond",
            (first_attempt, second_attempt),
        )

        with (
            patch.object(
                self.service,
                "_current_push_plan",
                return_value=("topic", "origin", "refs/heads/topic", True),
            ),
            patch.object(self.service, "status", return_value=[]),
            patch.object(self.service, "add_all", return_value=command_result(("add", "--all"))),
            patch.object(self.service, "staged_files", return_value=["scene.blend"]),
            patch.object(self.service, "next_quick_save_number", return_value=3),
            patch.object(self.service, "commit", return_value=commit_result),
            patch.object(self.service, "push_current", side_effect=push_error),
        ):
            with self.assertRaises(GitCommandError) as captured:
                self.service.quick_save(self.repository)

        self.assertEqual(captured.exception.attempts, (first_attempt, second_attempt))
        self.assertEqual(captured.exception.stderr, push_error.stderr)
        self.assertIn("Quick Save 3 was committed locally", str(captured.exception))


class PushCurrentTests(unittest.TestCase):
    def setUp(self):
        self.service = GitService("git", process=Mock(spec=ProcessService))
        self.repository = Path("C:/virtual/quick-save-repository")

    def test_existing_upstream_is_pushed_with_explicit_remote_and_refspec(self):
        remote = RemoteInfo(name="team", fetch_url="example", push_url="example")
        pushed = command_result(("push", "team", "topic:refs/heads/review/topic"))

        def config_value(key, _cwd):
            values = {
                "branch.topic.remote": "team",
                "branch.topic.merge": "refs/heads/review/topic",
            }
            return values.get(key, "")

        with (
            patch.object(self.service, "active_branch", return_value="topic"),
            patch.object(self.service, "remotes", return_value=[remote]),
            patch.object(self.service, "config_get", side_effect=config_value),
            patch.object(self.service, "_push_checked", return_value=pushed) as push_checked,
        ):
            result = self.service.push_current(self.repository, fallback_remote="origin")

        self.assertIs(result, pushed)
        push_checked.assert_called_once_with(
            ["push", "team", "topic:refs/heads/review/topic"],
            self.repository,
        )

    def test_missing_upstream_pushes_only_current_branch_and_sets_it(self):
        remote = RemoteInfo(name="origin", fetch_url="example", push_url="example")
        pushed = command_result(("push", "-u", "origin", "feature/materials:refs/heads/feature/materials"))

        with (
            patch.object(self.service, "active_branch", return_value="feature/materials"),
            patch.object(self.service, "remotes", return_value=[remote]),
            patch.object(self.service, "config_get", return_value=""),
            patch.object(self.service, "_push_checked", return_value=pushed) as push_checked,
        ):
            result = self.service.push_current(self.repository)

        self.assertIs(result, pushed)
        push_checked.assert_called_once_with(
            ["push", "-u", "origin", "feature/materials:refs/heads/feature/materials"],
            self.repository,
        )

    def test_missing_upstream_lock_recovery_uses_ephemeral_override(self):
        remote = RemoteInfo(name="origin", fetch_url="example", push_url="example")
        key = "lfs.https://github.com/octo-org/assets.git/info/lfs.locksverify"
        first = command_result(
            return_code=1,
            stderr=(
                'Remote "origin" does not support the Git LFS locking API. '
                "Consider disabling it with:\n"
                f"  $ git config {key} false"
            ),
        )
        second = command_result(stderr="Uploading LFS objects: 100%")
        self.service.process.run.side_effect = (first, second)
        push_arguments = [
            "push",
            "-u",
            "origin",
            "feature/materials:refs/heads/feature/materials",
        ]

        with (
            patch.object(self.service, "active_branch", return_value="feature/materials"),
            patch.object(self.service, "remotes", return_value=[remote]),
            patch.object(self.service, "config_get", return_value=""),
        ):
            result = self.service.push_current(self.repository)

        self.assertIs(result, second)
        self.assertEqual(
            self.service.process.run.call_args_list,
            [
                call("git", push_arguments, self.repository, 1800),
                call(
                    "git",
                    ["-c", f"{key}=false", *push_arguments],
                    self.repository,
                    1800,
                ),
            ],
        )


@unittest.skipUnless(shutil.which("git"), "Git is required for Quick Save integration tests")
class QuickSaveIntegrationTests(unittest.TestCase):
    def test_increments_and_pushes_active_branch_to_bare_remote(self):
        git_executable = shutil.which("git") or "git"
        process = ProcessService(echo_console=False)
        service = GitService(git_executable, process=process)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "working"
            remote = root / "remote.git"
            repository.mkdir()

            bare_init = process.run(git_executable, ["init", "--bare", str(remote)], timeout=30)
            self.assertTrue(bare_init.successful, bare_init.stderr)
            initialized = service.initialize(repository, "feature/materials")
            self.assertTrue(initialized.successful, initialized.stderr)
            service.config_set("user.name", "Quick Save Test", repository)
            service.config_set("user.email", "quick-save@example.com", repository)
            service.add_remote(repository, "origin", str(remote))

            scene = repository / "scene.blend"
            scene.write_text("version one", encoding="utf-8")

            first = service.quick_save(repository)
            self.assertEqual(first.message, "Quick Save 1")
            self.assertEqual(first.branch, "feature/materials")
            self.assertTrue(first.commit.successful, first.commit.stderr)
            self.assertTrue(first.push.successful, first.push.stderr)
            self.assertEqual(service.next_quick_save_number(repository), 2)

            first_local_head = process.run(git_executable, ["rev-parse", "HEAD"], repository, timeout=15)
            first_remote_head = process.run(
                git_executable,
                ["--git-dir", str(remote), "rev-parse", "refs/heads/feature/materials"],
                timeout=15,
            )
            self.assertTrue(first_local_head.successful, first_local_head.stderr)
            self.assertTrue(first_remote_head.successful, first_remote_head.stderr)
            self.assertEqual(first_remote_head.stdout, first_local_head.stdout)

            scene.write_text("version two", encoding="utf-8")
            second = service.quick_save(repository)
            self.assertEqual(second.message, "Quick Save 2")
            self.assertEqual(second.branch, "feature/materials")
            self.assertTrue(second.commit.successful, second.commit.stderr)
            self.assertTrue(second.push.successful, second.push.stderr)
            self.assertEqual(service.next_quick_save_number(repository), 3)

            second_local_head = process.run(git_executable, ["rev-parse", "HEAD"], repository, timeout=15)
            second_remote_head = process.run(
                git_executable,
                ["--git-dir", str(remote), "rev-parse", "refs/heads/feature/materials"],
                timeout=15,
            )
            self.assertTrue(second_local_head.successful, second_local_head.stderr)
            self.assertTrue(second_remote_head.successful, second_remote_head.stderr)
            self.assertNotEqual(second_local_head.stdout, first_local_head.stdout)
            self.assertEqual(second_remote_head.stdout, second_local_head.stdout)

            with self.assertRaisesRegex(GitCommandError, r"(?i)(no changes|no staged files)"):
                service.quick_save(repository)

            commit_count = process.run(
                git_executable,
                ["rev-list", "--count", "HEAD"],
                repository,
                timeout=15,
            )
            self.assertTrue(commit_count.successful, commit_count.stderr)
            self.assertEqual(commit_count.stdout, "2")
