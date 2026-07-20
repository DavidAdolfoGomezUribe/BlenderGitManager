from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call

from blender_git_manager.models import CommandResult, CommitInfo, FileChange, SyncStatus
from blender_git_manager.services.git_service import GitCommandError, GitService
from blender_git_manager.services.lfs_service import LFSService
from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.services.repository_service import RepositoryService
from blender_git_manager.utils.checkout import (
    plan_checkout_cleanup,
    remove_checkout_created_paths,
    repository_has_checkout_changes,
)

SHA1_A = "a" * 40
SHA1_B = "b" * 40
SHA256_C = "c" * 64


def command_result(
    *,
    stdout: str = "",
    stderr: str = "",
    return_code: int = 0,
) -> CommandResult:
    return CommandResult(
        executable="git",
        arguments=(),
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
    )


def commit_info(object_id: str, subject: str) -> CommitInfo:
    return CommitInfo(
        full_hash=object_id,
        parent_hashes=(),
        author_name="Test Author",
        author_email="test@example.com",
        authored_at="2026-07-20T12:00:00+00:00",
        decorations="",
        subject=subject,
    )


class CommitCommandTests(unittest.TestCase):
    def setUp(self):
        self.process = Mock(spec=ProcessService)
        self.service = GitService("git", process=self.process)
        self.repository = Path("C:/virtual/commit-checkout-repository")
        self.root = self.repository.resolve(strict=False)

    def test_resolve_commit_requires_a_full_hex_object_id(self):
        invalid_values = (
            "",
            "abc123",
            "a" * 39,
            "a" * 41,
            "g" * 40,
            f"{SHA1_A}^",
            f"{SHA1_A}\n",
            "HEAD",
            "--help",
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaisesRegex(
                GitCommandError,
                "full 40- or 64-character",
            ):
                self.service.resolve_commit(self.repository, value)

        self.process.run.assert_not_called()

    def test_resolves_only_an_exact_commit_and_accepts_sha256_length(self):
        self.process.run.return_value = command_result(stdout=SHA256_C.upper())

        resolved = self.service.resolve_commit(self.repository, SHA256_C.upper())

        self.assertEqual(resolved, SHA256_C)
        self.process.run.assert_called_once_with(
            "git",
            [
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{SHA256_C}^{{commit}}",
            ],
            self.repository,
            30,
        )

    def test_rejects_invalid_resolved_output(self):
        self.process.run.return_value = command_result(stdout="not-an-object")

        with self.assertRaisesRegex(GitCommandError, "Resolved commit"):
            self.service.resolve_commit(self.repository, SHA1_A)

    def test_head_commit_returns_exact_oid_or_empty_for_unborn_head(self):
        self.process.run.return_value = command_result(stdout=SHA1_A)
        self.assertEqual(self.service.head_commit(self.repository), SHA1_A)

        self.process.run.reset_mock()
        self.process.run.side_effect = (
            command_result(
                return_code=128,
                stderr="fatal: Needed a single revision",
            ),
            command_result(stdout="refs/heads/main"),
        )
        self.assertEqual(self.service.head_commit(self.repository), "")

    def test_head_branch_distinguishes_detached_head_from_command_errors(self):
        self.process.run.return_value = command_result(
            stdout=(
                f"# branch.oid {SHA1_A}\x00"
                "# branch.head feature/materials\x00"
            )
        )
        self.assertEqual(
            self.service.head_branch(self.repository),
            "feature/materials",
        )

        self.process.run.return_value = command_result(
            stdout=f"# branch.oid {SHA1_A}\x00# branch.head (detached)\x00"
        )
        self.assertEqual(self.service.head_branch(self.repository), "")

        self.process.run.return_value = command_result(
            return_code=128,
            stderr="fatal: not a git repository",
        )
        with self.assertRaisesRegex(GitCommandError, "not a git repository"):
            self.service.head_branch(self.repository)

    def test_head_commit_does_not_hide_git_failures_as_unborn(self):
        self.process.run.side_effect = (
            command_result(
                return_code=128,
                stderr="fatal: not a git repository",
            ),
            command_result(
                return_code=128,
                stderr="fatal: not a git repository",
            ),
        )

        with self.assertRaisesRegex(GitCommandError, "not a git repository"):
            self.service.head_commit(self.repository)

    def test_resolves_exact_local_branch_head(self):
        self.process.run.return_value = command_result(stdout=SHA1_A)

        resolved = self.service.branch_head_commit(
            self.repository,
            "feature/materials",
        )

        self.assertEqual(resolved, SHA1_A)
        self.process.run.assert_called_once_with(
            "git",
            [
                "rev-parse",
                "--verify",
                "--end-of-options",
                "refs/heads/feature/materials^{commit}",
            ],
            self.repository,
            30,
        )

    def test_checkout_resolves_then_switches_to_detached_head(self):
        self.process.run.side_effect = (
            command_result(stdout=SHA1_A),
            command_result(),
        )

        self.service.checkout_commit(self.repository, SHA1_A)

        self.assertEqual(
            self.process.run.call_args_list,
            [
                call(
                    "git",
                    [
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        f"{SHA1_A}^{{commit}}",
                    ],
                    self.repository,
                    30,
                ),
                call(
                    "git",
                    ["switch", "--detach", SHA1_A],
                    self.repository,
                    300,
                ),
            ],
        )

    def test_commit_info_rejects_metadata_for_a_different_commit(self):
        record = (
            f"{SHA1_B}\x1f\x1fTest Author\x1ftest@example.com"
            "\x1f2026-07-20T12:00:00+00:00\x1f\x1fWrong commit\x1f\x1e"
        )
        self.process.run.side_effect = (
            command_result(stdout=SHA1_A),
            command_result(stdout=record),
        )

        with self.assertRaisesRegex(GitCommandError, "instead of requested commit"):
            self.service.commit_info(self.repository, SHA1_A)

    def test_commit_tree_requires_the_exact_regular_file(self):
        self.process.run.side_effect = (
            command_result(stdout=SHA1_A),
            command_result(
                stdout=(
                    f"100644 blob {SHA1_B}\tscenes/main[final].blend\x00"
                    f"120000 blob {SHA1_B}\tscenes/link.blend\x00"
                )
            ),
        )

        self.assertTrue(
            self.service.commit_contains_regular_file(
                self.repository,
                SHA1_A,
                "scenes/main[final].blend",
            )
        )
        self.assertEqual(
            self.process.run.call_args_list[-1],
            call(
                "git",
                [
                    "--literal-pathspecs",
                    "ls-tree",
                    "-r",
                    "-z",
                    SHA1_A,
                    "--",
                    "scenes/main[final].blend",
                ],
                self.root,
                30,
            ),
        )

    def test_repository_dirty_check_includes_all_untracked_files(self):
        self.process.run.return_value = command_result(stdout="?? assets/new texture.png\x00")

        self.assertTrue(self.service.repository_has_changes(self.repository))
        self.process.run.assert_called_once_with(
            "git",
            [
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ],
            self.root,
            30,
        )

        self.process.run.reset_mock()
        self.process.run.return_value = command_result(stdout="")
        self.assertFalse(self.service.repository_has_changes(self.repository))

    def test_restore_uses_exact_commit_and_literal_path(self):
        self.process.run.side_effect = (
            command_result(stdout=SHA1_A),
            command_result(),
        )

        self.service.restore_path_from_commit(
            self.repository,
            SHA1_A,
            "scenes/main[final].blend",
        )

        self.assertEqual(
            self.process.run.call_args_list[-1],
            call(
                "git",
                [
                    "--literal-pathspecs",
                    "restore",
                    "--source",
                    SHA1_A,
                    "--staged",
                    "--worktree",
                    "--",
                    "scenes/main[final].blend",
                ],
                self.root,
                300,
            ),
        )

    def test_tree_delta_and_whole_tree_restore_use_exact_commits(self):
        source_tree = (
            f"100644 blob {SHA1_B}\tscene.blend\x00"
            f"100644 blob {SHA1_B}\tassets/shared.txt\x00"
        )
        target_tree = (
            f"100644 blob {SHA1_B}\tscene.blend\x00"
            f"100644 blob {SHA1_B}\tassets/shared.txt\x00"
            f"100644 blob {SHA1_B}\tassets/only-target.txt\x00"
            f"120000 blob {SHA1_B}\tassets/target-link\x00"
            f"160000 commit {SHA1_B}\tvendor/submodule\x00"
        )
        self.process.run.side_effect = (
            command_result(stdout=SHA1_A),
            command_result(stdout=source_tree),
            command_result(stdout=SHA1_B),
            command_result(stdout=target_tree),
        )

        added = self.service.checkout_added_file_paths(
            self.repository,
            SHA1_A,
            SHA1_B,
        )

        self.assertEqual(
            added,
            ("assets/only-target.txt", "assets/target-link"),
        )

        self.process.run.reset_mock()
        self.process.run.side_effect = (
            command_result(stdout=SHA1_A),
            command_result(),
        )
        self.service.restore_tree_from_commit(self.repository, SHA1_A)
        self.assertEqual(
            self.process.run.call_args_list[-1],
            call(
                "git",
                [
                    "--literal-pathspecs",
                    "restore",
                    "--source",
                    SHA1_A,
                    "--staged",
                    "--worktree",
                    "--",
                    ".",
                ],
                self.root,
                600,
            ),
        )


class RepositorySnapshotHeadTests(unittest.TestCase):
    def setUp(self):
        self.git = Mock(spec=GitService)
        self.lfs = Mock(spec=LFSService)
        self.repository = RepositoryService(git=self.git, lfs=self.lfs)
        self.root = Path("C:/virtual/snapshot-repository").resolve(strict=False)

        self.git.detect_root.return_value = self.root
        self.git.remotes.return_value = []
        self.git.status.return_value = []
        self.git.branches.return_value = []
        self.git.sync_status.return_value = SyncStatus()
        self.git.head_branch.return_value = "main"
        self.lfs.is_active.return_value = False

    def test_last_commit_is_head_not_first_log_all_result(self):
        other = commit_info(SHA1_B, "newer commit on another branch")
        head = commit_info(SHA1_A, "current branch HEAD")
        self.git.history.return_value = [other, head]
        self.git.head_commit.return_value = SHA1_A

        snapshot = self.repository.snapshot(self.root)

        self.assertEqual(snapshot.head_commit, SHA1_A)
        self.assertIs(snapshot.last_commit, head)
        self.git.commit_info.assert_not_called()

    def test_fetches_exact_head_metadata_when_history_limit_omits_it(self):
        other = commit_info(SHA1_B, "newer commit on another branch")
        head = commit_info(SHA1_A, "current branch HEAD")
        self.git.history.return_value = [other]
        self.git.head_commit.return_value = SHA1_A
        self.git.commit_info.return_value = head

        snapshot = self.repository.snapshot(self.root, history_limit=1)

        self.assertIs(snapshot.last_commit, head)
        self.git.commit_info.assert_called_once_with(self.root, SHA1_A)


class CheckoutStatusTests(unittest.TestCase):
    def test_ignores_only_untracked_legacy_internal_backups(self):
        git = Mock(spec=GitService)
        repository = Path("C:/virtual/repository")
        git.status.return_value = [
            FileChange(
                index_status="?",
                worktree_status="?",
                path=".blender_git_backups/scene_backup.blend",
            )
        ]
        self.assertFalse(repository_has_checkout_changes(git, repository))

        git.status.return_value = [
            FileChange(
                index_status=" ",
                worktree_status="M",
                path=".blender_git_backups/tracked.blend",
            )
        ]
        self.assertTrue(repository_has_checkout_changes(git, repository))

        git.status.return_value = [
            FileChange(
                index_status="?",
                worktree_status="?",
                path="assets/new-texture.png",
            )
        ]
        self.assertTrue(repository_has_checkout_changes(git, repository))

    def test_cleanup_removes_only_target_files_proven_absent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            planned = plan_checkout_cleanup(
                root,
                ("scene.blend",),
                ("assets/only-target.txt",),
            )
            self.assertEqual(planned, ("assets/only-target.txt",))

            created = root / "assets" / "only-target.txt"
            created.parent.mkdir()
            created.write_text("partial checkout", encoding="utf-8")
            remove_checkout_created_paths(root, planned)

            self.assertFalse(created.exists())
            self.assertTrue(created.parent.is_dir())

    def test_cleanup_refuses_preexisting_or_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            existing = root / "do-not-delete.txt"
            existing.write_text("user file", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "would overwrite"):
                plan_checkout_cleanup(
                    root,
                    (),
                    ("do-not-delete.txt",),
                )
            with self.assertRaisesRegex(RuntimeError, "unsafe checkout path|escapes"):
                plan_checkout_cleanup(
                    root,
                    (),
                    ("../outside.txt",),
                )
            self.assertEqual(existing.read_text(encoding="utf-8"), "user file")

@unittest.skipUnless(shutil.which("git"), "Git is required for integration tests")
class CommitCheckoutIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "CommitCheckout"
        self.root.mkdir()
        self.git = GitService(
            shutil.which("git") or "git",
            process=ProcessService(echo_console=False),
        )
        self.git.initialize(self.root, "main")
        self.git.config_set("user.name", "Blender Git Manager Test", self.root)
        self.git.config_set("user.email", "test@example.com", self.root)

    def _commit_all(self, message: str) -> str:
        self.git.add_all(self.root)
        self.git.commit(self.root, message)
        return self.git.head_commit(self.root)

    def test_detached_checkout_materializes_the_entire_commit(self):
        scene = self.root / "scene.blend"
        sidecar = self.root / "assets" / "marker.txt"
        sidecar.parent.mkdir()
        scene.write_bytes(b"BLENDER-v1")
        sidecar.write_text("version one", encoding="utf-8")
        first = self._commit_all("Version one")

        scene.write_bytes(b"BLENDER-v2")
        sidecar.write_text("version two", encoding="utf-8")
        self._commit_all("Version two")

        self.assertFalse(self.git.repository_has_changes(self.root))
        self.assertTrue(
            self.git.commit_contains_regular_file(self.root, first, "scene.blend")
        )

        self.git.checkout_commit(self.root, first)

        self.assertEqual(self.git.active_branch(self.root), "")
        self.assertEqual(self.git.head_commit(self.root), first)
        self.assertEqual(scene.read_bytes(), b"BLENDER-v1")
        self.assertEqual(sidecar.read_text(encoding="utf-8"), "version one")
        self.assertFalse(self.git.repository_has_changes(self.root))

        sidecar.write_text("temporary edit", encoding="utf-8")
        self.assertTrue(self.git.repository_has_changes(self.root))
        self.git.restore_path_from_commit(self.root, first, sidecar)
        self.assertEqual(sidecar.read_text(encoding="utf-8"), "version one")
        self.assertFalse(self.git.repository_has_changes(self.root))

    def test_missing_lfs_object_can_restore_the_entire_source_tree(self):
        lfs = LFSService(self.git.executable, self.git.process)
        if not lfs.version().successful:
            self.skipTest("Git LFS is required for the missing-object rollback test")
        lfs.initialize_local(self.root)
        lfs.track(self.root, "*.blend")

        scene = self.root / "scene.blend"
        sidecar = self.root / "sidecar.txt"
        target_only = self.root / "only-target.txt"
        scene.write_bytes(b"BLENDER-target")
        sidecar.write_text("target sidecar", encoding="utf-8")
        target_only.write_text("target only", encoding="utf-8")
        target = self._commit_all("LFS target")
        target_oid = next(
            item.oid for item in lfs.ls_files(self.root) if item.path == "scene.blend"
        )

        scene.write_bytes(b"BLENDER-source")
        sidecar.write_text("source sidecar", encoding="utf-8")
        target_only.unlink()
        source = self._commit_all("LFS source")

        cleanup_paths = plan_checkout_cleanup(
            self.root,
            self.git.commit_tree_paths(self.root, source),
            self.git.checkout_added_file_paths(self.root, source, target),
        )
        self.assertEqual(cleanup_paths, ("only-target.txt",))

        lfs_object = (
            self.root
            / ".git"
            / "lfs"
            / "objects"
            / target_oid[:2]
            / target_oid[2:4]
            / target_oid
        )
        self.assertTrue(lfs_object.is_file())
        lfs_object.unlink()

        with self.assertRaises(GitCommandError):
            self.git.checkout_commit(self.root, target)

        current_branch = self.git.head_branch(self.root)
        current_commit = self.git.head_commit(self.root)
        self.assertEqual(current_branch, "main")
        self.assertEqual(current_commit, source)
        self.assertTrue(repository_has_checkout_changes(self.git, self.root))
        self.assertTrue(target_only.is_file())
        if current_branch != "main" or current_commit != source:
            self.git.restore_tree_from_commit(self.root, source)
            remove_checkout_created_paths(self.root, cleanup_paths)
            try:
                self.git.switch_branch(self.root, "main")
            except GitCommandError:
                pass
        if repository_has_checkout_changes(self.git, self.root):
            self.git.restore_tree_from_commit(self.root, source)
        remove_checkout_created_paths(self.root, cleanup_paths)

        self.assertEqual(self.git.head_branch(self.root), "main")
        self.assertEqual(self.git.head_commit(self.root), source)
        self.assertEqual(scene.read_bytes(), b"BLENDER-source")
        self.assertEqual(sidecar.read_text(encoding="utf-8"), "source sidecar")
        self.assertFalse(target_only.exists())
        self.assertFalse(repository_has_checkout_changes(self.git, self.root))


if __name__ == "__main__":
    unittest.main()
