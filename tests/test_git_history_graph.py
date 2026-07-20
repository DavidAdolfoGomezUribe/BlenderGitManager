from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from blender_git_manager.models import (
    CommitReferenceKind,
    HistoryQuery,
)
from blender_git_manager.services.git_service import GitCommandError, GitService
from blender_git_manager.services.history_service import HistoryService
from blender_git_manager.services.process_service import ProcessService


@unittest.skipUnless(shutil.which("git"), "Git is required for integration tests")
class GitHistoryGraphIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git = GitService(
            shutil.which("git") or "git",
            process=ProcessService(echo_console=False),
        )
        self._run("init", "-b", "main")
        self._run("config", "user.name", "Graph Test")
        self._run("config", "user.email", "graph@example.invalid")

        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        self._commit_all("base")
        self.base = self.git.head_commit(self.root)

        self._run("switch", "-c", "feature")
        (self.root / "feature.txt").write_text("feature\n", encoding="utf-8")
        self._commit_all("feature work")
        self.feature = self.git.head_commit(self.root)

        self._run("switch", "main")
        (self.root / "main.txt").write_text("main\n", encoding="utf-8")
        self._commit_all("main work")
        self.main_work = self.git.head_commit(self.root)
        self._run("merge", "--no-ff", "feature", "-m", "merge feature")
        self.merge = self.git.head_commit(self.root)
        self._run("tag", "v1.0", self.feature)
        self._run("remote", "add", "origin", "https://github.com/example/project.git")
        self._run("update-ref", "refs/remotes/origin/main", self.merge)

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, *arguments: str):
        return self.git._run_checked(list(arguments), self.root, timeout=60)

    def _commit_all(self, message: str):
        self._run("add", "--all")
        self._run("commit", "-m", message)

    def test_structured_history_layout_refs_filters_and_details(self):
        page = HistoryService(self.git).load(
            self.root,
            HistoryQuery(limit=100),
        )

        self.assertEqual(page.commits[0].full_hash, self.merge)
        self.assertTrue(page.commits[0].is_merge)
        self.assertEqual(len(page.commits[0].parent_lane_indexes), 2)
        positions = {
            commit.full_hash: index for index, commit in enumerate(page.commits)
        }
        for commit in page.commits:
            for parent in commit.parent_hashes:
                if parent in positions:
                    self.assertGreater(positions[parent], positions[commit.full_hash])

        merge_references = {
            (reference.kind, reference.name)
            for reference in page.commits[0].references
        }
        self.assertIn((CommitReferenceKind.HEAD, "HEAD"), merge_references)
        self.assertIn(
            (CommitReferenceKind.LOCAL_BRANCH, "main"),
            merge_references,
        )
        self.assertIn(
            (CommitReferenceKind.REMOTE_BRANCH, "origin/main"),
            merge_references,
        )
        feature_commit = next(
            commit for commit in page.commits if commit.full_hash == self.feature
        )
        self.assertIn(
            (CommitReferenceKind.TAG, "v1.0"),
            {(reference.kind, reference.name) for reference in feature_commit.references},
        )

        branch_page = HistoryService(self.git).load(
            self.root,
            HistoryQuery(limit=100, branch_filter="feature"),
        )
        hashes = {commit.full_hash for commit in branch_page.commits}
        self.assertEqual(hashes, {self.feature, self.base})

        filtered = HistoryService(self.git).filter(page, "feature", "graph@")
        self.assertTrue(filtered.commits)
        self.assertTrue(
            all("feature" in commit.subject.casefold() for commit in filtered.commits)
        )

        details = self.git.commit_details(self.root, self.merge)
        self.assertEqual(details.full_hash, self.merge)
        self.assertIn("feature.txt", {file.path for file in details.files})
        self.assertGreaterEqual(details.changed_files, 1)

        second_parent_details = self.git.commit_details(
            self.root,
            self.merge,
            mainline=2,
        )
        self.assertIn(
            "main.txt",
            {file.path for file in second_parent_details.files},
        )

        root_details = self.git.commit_details(self.root, self.base)
        self.assertIn("base.txt", {file.path for file in root_details.files})

        signature = self.git.reference_signature(self.root)
        self.assertEqual(len(signature), 64)

        self._run(
            "update-ref",
            "refs/remotes/unconfigured/topic",
            self.feature,
        )
        self.assertNotEqual(self.git.reference_signature(self.root), signature)
        branch = next(
            item
            for item in self.git.branches(self.root)
            if item.name == "unconfigured/topic"
        )
        self.assertTrue(branch.remote)
        remote_page = HistoryService(self.git).load(
            self.root,
            HistoryQuery(limit=100, branch_filter="unconfigured/topic"),
        )
        self.assertEqual(
            {commit.full_hash for commit in remote_page.commits},
            {self.feature, self.base},
        )

        self._run("branch", "origin/main", self.base)
        colliding = {
            branch.full_ref: branch
            for branch in self.git.branches(self.root)
            if branch.full_ref
            in {"refs/heads/origin/main", "refs/remotes/origin/main"}
        }
        self.assertEqual(
            set(colliding),
            {"refs/heads/origin/main", "refs/remotes/origin/main"},
        )
        self.assertEqual(
            {
                commit.full_hash
                for commit in HistoryService(self.git)
                .load(
                    self.root,
                    HistoryQuery(
                        limit=100,
                        branch_filter=colliding["refs/heads/origin/main"].name,
                    ),
                )
                .commits
            },
            {self.base},
        )
        self.assertIn(
            self.merge,
            {
                commit.full_hash
                for commit in HistoryService(self.git)
                .load(
                    self.root,
                    HistoryQuery(
                        limit=100,
                        branch_filter=colliding[
                            "refs/remotes/origin/main"
                        ].name,
                    ),
                )
                .commits
            },
        )

        tree = self._run("write-tree").stdout.strip()
        detached_orphan = self._run(
            "commit-tree",
            tree,
            "-m",
            "detached orphan",
        ).stdout.strip()
        self._run("checkout", "--detach", detached_orphan)
        detached_page = HistoryService(self.git).load(
            self.root,
            HistoryQuery(limit=100),
        )
        detached_commit = next(
            commit
            for commit in detached_page.commits
            if commit.full_hash == detached_orphan
        )
        self.assertIn(
            (CommitReferenceKind.HEAD, "HEAD"),
            {
                (reference.kind, reference.name)
                for reference in detached_commit.references
            },
        )

    def test_exact_branch_tag_creation_and_revert(self):
        self.git.create_branch_at(self.root, "from-base", self.base)
        self.assertEqual(
            self.git.branch_head_commit(self.root, "from-base"),
            self.base,
        )
        self.git.create_tag_at(self.root, "selected-tag", self.feature)
        tagged = self._run(
            "rev-parse",
            "--verify",
            "refs/tags/selected-tag^{commit}",
        ).stdout.strip()
        self.assertEqual(tagged, self.feature)

        (self.root / "revert-me.txt").write_text("temporary\n", encoding="utf-8")
        self._commit_all("change to revert")
        target = self.git.head_commit(self.root)
        result = self.git.revert_commit(self.root, target)

        self.assertTrue(result.successful)
        self.assertFalse((self.root / "revert-me.txt").exists())
        self.assertFalse(self.git.repository_has_changes(self.root))
        self.assertNotEqual(self.git.head_commit(self.root), target)

        (self.root / "base.txt").write_text(
            "change protected by failing hook\n",
            encoding="utf-8",
        )
        self._commit_all("hook rollback target")
        hook_target = self.git.head_commit(self.root)
        hook = self.root / ".git" / "hooks" / "prepare-commit-msg"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
        hook.chmod(0o755)

        with self.assertRaises(GitCommandError) as raised:
            self.git.revert_commit(self.root, hook_target)

        self.assertIn("pre-revert state", str(raised.exception))
        self.assertEqual(self.git.head_commit(self.root), hook_target)
        self.assertEqual(
            (self.root / "base.txt").read_text(encoding="utf-8"),
            "change protected by failing hook\n",
        )
        self.assertFalse(self.git.repository_has_changes(self.root))


if __name__ == "__main__":
    unittest.main()
