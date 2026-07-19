from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blender_git_manager.services.history_parser import FIELD_SEPARATOR, RECORD_SEPARATOR, parse_git_log
from blender_git_manager.services.status_parser import parse_porcelain_v1


class ParserTests(unittest.TestCase):
    def test_status_parser(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tank.blend").write_bytes(b"1234")
            changes = parse_porcelain_v1("M  tank.blend\n?? notes.txt\nR  old.png -> new.png", root)
        self.assertEqual(len(changes), 3)
        self.assertTrue(changes[0].staged)
        self.assertEqual(changes[0].size_bytes, 4)
        self.assertTrue(changes[1].untracked)
        self.assertEqual(changes[2].original_path, "old.png")
        self.assertEqual(changes[2].path, "new.png")

    def test_history_parser(self):
        fields = [
            "abcdef123456",
            "parent1 parent2",
            "David",
            "david@example.com",
            "2026-07-19T10:00:00-05:00",
            "HEAD -> main, origin/main",
            "Merge materials",
            "Extended body",
        ]
        output = FIELD_SEPARATOR.join(fields) + RECORD_SEPARATOR
        commits = parse_git_log(output)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0].short_hash, "abcdef12")
        self.assertTrue(commits[0].is_merge)
        self.assertEqual(commits[0].subject, "Merge materials")
