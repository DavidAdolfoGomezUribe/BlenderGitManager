from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from blender_git_manager.models import InitConfig
from blender_git_manager.services.git_service import GitService
from blender_git_manager.services.repository_service import RepositoryService


@unittest.skipUnless(shutil.which("git"), "Git is required for integration tests")
class GitIntegrationTests(unittest.TestCase):
    def test_initialize_commit_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "TankAssets"
            root.mkdir()
            (root / "tank.txt").write_text("v1", encoding="utf-8")
            service = RepositoryService(git=GitService(shutil.which("git") or "git"))
            report = service.initialize_repository(
                InitConfig(
                    repository_path=root,
                    repository_name="TankAssets",
                    initial_branch="main",
                    author_name="Blender Git Manager Test",
                    author_email="test@example.com",
                    enable_lfs=False,
                    create_initial_commit=True,
                    stage_mode="ALL",
                    connect_github=False,
                )
            )
            self.assertTrue(report.successful, report.steps)
            self.assertTrue(report.initial_commit_hash)
            snapshot = service.snapshot(root)
            self.assertEqual(snapshot.active_branch, "main")
            self.assertEqual(len(snapshot.commits), 1)
            self.assertEqual(len(snapshot.changes), 0)

            (root / "tank.txt").write_text("v2", encoding="utf-8")
            changes = service.git.status(root)
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0].worktree_status, "M")
