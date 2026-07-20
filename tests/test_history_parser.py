from __future__ import annotations

import unittest

from blender_git_manager.models import CommitInfo
from blender_git_manager.services.history_parser import (
    FIELD_SEPARATOR,
    RECORD_SEPARATOR,
    HistoryParser,
    ParsedHistoryCommit,
    normalize_references,
    parse_git_log,
    parse_history,
)


def structured_record(*fields: str) -> str:
    return FIELD_SEPARATOR.join(fields) + RECORD_SEPARATOR


class HistoryParserTests(unittest.TestCase):
    def test_parses_requested_seven_field_format_and_unicode(self):
        output = structured_record(
            "a" * 40,
            f"{'b' * 40} {'c' * 40}",
            "Davián Gómez",
            "davian@example.com",
            "2026-07-20T14:30:00-05:00",
            "HEAD -> main, origin/main, tag: versión-1",
            "Mezcla de iluminación 🎨",
        )

        commits = parse_history(output)

        self.assertEqual(len(commits), 1)
        commit = commits[0]
        self.assertIsInstance(commit, ParsedHistoryCommit)
        self.assertEqual(commit.hash, "a" * 40)
        self.assertEqual(commit.short_hash, "a" * 8)
        self.assertEqual(commit.parent_hashes, ("b" * 40, "c" * 40))
        self.assertEqual(commit.author_name, "Davián Gómez")
        self.assertEqual(commit.date, "2026-07-20T14:30:00-05:00")
        self.assertEqual(commit.message, "Mezcla de iluminación 🎨")
        self.assertEqual(commit.raw_references, "HEAD -> main, origin/main, tag: versión-1")
        self.assertEqual(commit.references, ("HEAD", "main", "origin/main", "versión-1"))
        self.assertTrue(commit.is_merge)

    def test_preserves_separator_characters_in_last_field(self):
        message = f"Subject containing {FIELD_SEPARATOR} a unit separator"
        output = structured_record(
            "1234567890abcdef",
            "",
            "Author",
            "author@example.com",
            "2026-07-20T14:30:00Z",
            "",
            message,
        )

        commits = HistoryParser.parse(output)

        self.assertEqual(commits[0].message, message)

    def test_ignores_empty_and_incomplete_records_without_raising(self):
        incomplete = FIELD_SEPARATOR.join(
            ("deadbeef", "", "Author", "author@example.com", "2026-07-20T14:30:00Z")
        )
        complete = FIELD_SEPARATOR.join(
            ("cafebabe", "", "Author", "author@example.com", "2026-07-20T14:30:00Z", "", "Complete")
        )
        output = RECORD_SEPARATOR + incomplete + RECORD_SEPARATOR + complete

        commits = parse_history(output)

        self.assertEqual([commit.hash for commit in commits], ["cafebabe"])

    def test_parses_multiple_records_without_final_record_separator(self):
        first = structured_record(
            "11111111",
            "",
            "First",
            "first@example.com",
            "2026-07-20T10:00:00Z",
            "",
            "First commit",
        )
        second = FIELD_SEPARATOR.join(
            (
                "22222222",
                "11111111",
                "Second",
                "second@example.com",
                "2026-07-20T11:00:00Z",
                "feature",
                "Second commit",
            )
        )

        commits = parse_history(first + "\n" + second)

        self.assertEqual([commit.hash for commit in commits], ["11111111", "22222222"])
        self.assertEqual(commits[1].parent_hashes, ("11111111",))

    def test_normalizes_decorated_and_fully_qualified_references(self):
        references = normalize_references(
            "HEAD -> refs/heads/main, refs/remotes/origin/main, "
            "tag: release-1, refs/tags/release-1, "
            "tag: refs/tags/release-2, origin/HEAD -> origin/main"
        )

        self.assertEqual(
            references,
            (
                "HEAD",
                "main",
                "origin/main",
                "release-1",
                "release-2",
                "origin/HEAD",
            ),
        )

    def test_existing_parse_git_log_api_keeps_body_and_commit_info(self):
        body = f"Extended description\nwith Unicode áéí\nand {FIELD_SEPARATOR} delimiter"
        output = structured_record(
            "abcdef123456",
            "parent1 parent2",
            "David",
            "david@example.com",
            "2026-07-19T10:00:00-05:00",
            "HEAD -> main, origin/main",
            "Merge materials",
            body,
        )

        commits = parse_git_log(output)

        self.assertEqual(len(commits), 1)
        self.assertIsInstance(commits[0], CommitInfo)
        self.assertEqual(commits[0].short_hash, "abcdef12")
        self.assertTrue(commits[0].is_merge)
        self.assertEqual(commits[0].subject, "Merge materials")
        self.assertEqual(commits[0].body, body)

    def test_empty_output_returns_empty_collection(self):
        self.assertEqual(parse_history(""), [])
        self.assertEqual(parse_git_log(""), [])


if __name__ == "__main__":
    unittest.main()
