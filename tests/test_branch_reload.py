from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from blender_git_manager.models import CommandResult
from blender_git_manager.services.git_service import GitCommandError, GitService
from blender_git_manager.services.process_service import ProcessService
from blender_git_manager.utils.blend_files import (
    BlendFileValidationError,
    validate_blend_file_for_reload,
)


def command_result(*, stdout: str = "", return_code: int = 0) -> CommandResult:
    return CommandResult(
        executable="git",
        arguments=(),
        return_code=return_code,
        stdout=stdout,
    )


class BlendFileValidationTests(unittest.TestCase):
    def test_accepts_blender_file_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            headers = (
                b"BLENDER-v300-test",
                b"\x1f\x8bcompressed-blend",
                b"\x28\xb5\x2f\xfdcompressed-blend",
            )

            for index, header in enumerate(headers):
                with self.subTest(header=header):
                    path = root / f"scene-{index}.blend"
                    path.write_bytes(header)
                    self.assertEqual(validate_blend_file_for_reload(path), path.resolve())

    def test_rejects_unresolved_git_lfs_pointer(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scene.blend"
            path.write_bytes(
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha256:0123456789\n"
            )

            with self.assertRaisesRegex(BlendFileValidationError, "Git LFS pointer"):
                validate_blend_file_for_reload(path)

    def test_rejects_missing_or_invalid_blender_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = root / "invalid.blend"
            invalid.write_bytes(b"not a blend file")

            with self.assertRaisesRegex(BlendFileValidationError, "not a valid Blender file"):
                validate_blend_file_for_reload(invalid)
            with self.assertRaisesRegex(BlendFileValidationError, "does not exist"):
                validate_blend_file_for_reload(root / "missing.blend")


class BranchTreeTests(unittest.TestCase):
    def setUp(self):
        self.process = Mock(spec=ProcessService)
        self.service = GitService("git", process=self.process)
        self.repository = Path("C:/virtual/branch-reload-repository")

    def test_finds_exact_regular_file_with_literal_pathspec(self):
        self.process.run.return_value = command_result(
            stdout=(
                "100644 blob 0123456789abcdef\tscenes/main[final].blend\x00"
                "100644 blob fedcba9876543210\tscenes/other.blend\x00"
            )
        )

        exists = self.service.branch_contains_regular_file(
            self.repository,
            "feature/materials",
            Path("scenes/main[final].blend"),
        )

        self.assertTrue(exists)
        self.process.run.assert_called_once_with(
            "git",
            [
                "--literal-pathspecs",
                "ls-tree",
                "-r",
                "-z",
                "refs/heads/feature/materials",
                "--",
                "scenes/main[final].blend",
            ],
            self.repository.resolve(strict=False),
            30,
        )

    def test_rejects_symlink_missing_and_outside_paths(self):
        self.process.run.return_value = command_result(
            stdout="120000 blob 0123456789abcdef\tscene.blend\x00"
        )
        self.assertFalse(
            self.service.branch_contains_regular_file(
                self.repository,
                "feature",
                "scene.blend",
            )
        )

        self.process.run.return_value = command_result(stdout="")
        self.assertFalse(
            self.service.branch_contains_regular_file(
                self.repository,
                "feature",
                "missing.blend",
            )
        )

        with self.assertRaises(GitCommandError):
            self.service.branch_contains_regular_file(
                self.repository,
                "feature",
                self.repository.parent / "outside.blend",
            )

    def test_detects_git_changes_for_exact_file_only(self):
        self.process.run.return_value = command_result(
            stdout=" M scene.blend\x00",
        )
        self.assertTrue(
            self.service.path_has_changes(
                self.repository,
                "scene.blend",
            )
        )
        self.process.run.assert_called_once_with(
            "git",
            [
                "--literal-pathspecs",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                "scene.blend",
            ],
            self.repository.resolve(strict=False),
            30,
        )

        self.process.reset_mock()
        self.process.run.return_value = command_result(stdout="")
        self.assertFalse(
            self.service.path_has_changes(
                self.repository,
                "scene.blend",
            )
        )

    def test_restores_exact_file_from_full_local_branch_ref(self):
        self.process.run.return_value = command_result()

        self.service.restore_path_from_branch(
            self.repository,
            "main",
            Path("scenes/main[final].blend"),
        )

        self.process.run.assert_called_once_with(
            "git",
            [
                "--literal-pathspecs",
                "restore",
                "--source",
                "refs/heads/main",
                "--staged",
                "--worktree",
                "--",
                "scenes/main[final].blend",
            ],
            self.repository.resolve(strict=False),
            300,
        )


if __name__ == "__main__":
    unittest.main()
