from __future__ import annotations

import unittest
from pathlib import Path

from blender_git_manager.models import (
    CommitDetails,
    CommitFileStat,
    CommitInfo,
    CommitReference,
    CommitReferenceKind,
    HistoryQuery,
)
from blender_git_manager.services.history_parser import ParsedHistoryCommit
from blender_git_manager.services.history_service import (
    HistoryService,
    filter_history_page,
    parse_commit_references,
)


def commit(
    object_id: str,
    parents: tuple[str, ...] = (),
    *,
    author: str = "David",
    email: str = "david@example.com",
    subject: str = "",
    body: str = "",
    decorations: str = "",
) -> CommitInfo:
    return CommitInfo(
        full_hash=object_id,
        parent_hashes=parents,
        author_name=author,
        author_email=email,
        authored_at="2026-07-20T12:00:00-05:00",
        decorations=decorations,
        subject=subject or object_id,
        body=body,
    )


class FakeHistoryBackend:
    def __init__(
        self,
        commits: list[CommitInfo | ParsedHistoryCommit],
        details: CommitDetails | None = None,
    ) -> None:
        self.commits = commits
        self.details = details
        self.history_calls: list[tuple[Path, HistoryQuery, int]] = []
        self.detail_calls: list[tuple[Path, str]] = []

    def history_graph(self, cwd, query, max_count):
        root = Path(cwd)
        self.history_calls.append((root, query, max_count))
        return self.commits[query.offset : query.offset + max_count]

    def commit_details(self, cwd, full_hash):
        self.detail_calls.append((Path(cwd), full_hash))
        if self.details is None:
            raise AssertionError("No fake details configured.")
        return self.details


class HistoryQueryTests(unittest.TestCase):
    def test_defaults_and_next_page_are_typed_and_bounded(self):
        query = HistoryQuery()

        self.assertEqual(query.limit, 200)
        self.assertEqual(query.offset, 0)
        self.assertTrue(query.show_all_branches)
        self.assertTrue(query.show_remotes)
        self.assertTrue(query.show_tags)
        self.assertEqual(query.next_page().offset, 200)

    def test_normalizes_branch_filter(self):
        self.assertEqual(HistoryQuery(branch_filter="  feature/render  ").branch_filter, "feature/render")

    def test_rejects_invalid_limits_and_offsets(self):
        for invalid_limit in (99, 1001, True, 2.5):
            with self.subTest(limit=invalid_limit), self.assertRaises((TypeError, ValueError)):
                HistoryQuery(limit=invalid_limit)
        for invalid_offset in (-1, True, 1.5):
            with self.subTest(offset=invalid_offset), self.assertRaises((TypeError, ValueError)):
                HistoryQuery(offset=invalid_offset)


class CommitReferenceTests(unittest.TestCase):
    def test_parses_head_local_remote_tag_and_symbolic_remote(self):
        references = parse_commit_references(
            "HEAD -> refs/heads/main, refs/remotes/origin/main, tag: v1.2, "
            "origin/HEAD -> origin/main, refs/notes/reviewed"
        )

        self.assertEqual(
            references,
            (
                CommitReference("HEAD", CommitReferenceKind.HEAD, "main"),
                CommitReference("main", CommitReferenceKind.LOCAL_BRANCH),
                CommitReference("origin/main", CommitReferenceKind.REMOTE_BRANCH),
                CommitReference("v1.2", CommitReferenceKind.TAG),
                CommitReference(
                    "origin/HEAD",
                    CommitReferenceKind.REMOTE_BRANCH,
                    "origin/main",
                ),
                CommitReference("refs/notes/reviewed", CommitReferenceKind.OTHER),
            ),
        )

    def test_empty_and_duplicate_decorations_are_safe(self):
        self.assertEqual(parse_commit_references(""), ())
        self.assertEqual(
            parse_commit_references("tag: v1, refs/tags/v1"),
            (CommitReference("v1", CommitReferenceKind.TAG),),
        )


class HistoryServiceTests(unittest.TestCase):
    def test_load_requests_sentinel_and_builds_merge_layout(self):
        merge = commit("M", ("A", "B"), decorations="HEAD -> main, tag: v2")
        first_parent = commit("A", ("R",))
        second_parent = commit("B", ("R",), decorations="origin/feature")
        root = commit("R")
        backend = FakeHistoryBackend([merge, first_parent, second_parent, root])
        query = HistoryQuery(limit=100, branch_filter="main")

        page = HistoryService(backend).load("repo", query)

        self.assertEqual(backend.history_calls, [(Path("repo"), query, 101)])
        self.assertFalse(page.has_more)
        self.assertEqual([item.hash for item in page.commits], ["M", "A", "B", "R"])
        self.assertEqual(page.commits[0].lane_index, 0)
        self.assertEqual(page.commits[0].parent_lane_indexes, (0, 1))
        self.assertTrue(page.commits[0].is_merge)
        self.assertEqual(
            [reference.kind for reference in page.commits[0].references],
            [
                CommitReferenceKind.HEAD,
                CommitReferenceKind.LOCAL_BRANCH,
                CommitReferenceKind.TAG,
            ],
        )

    def test_load_limits_visible_page_and_exposes_next_query(self):
        commits = [
            commit(f"{number:040x}", (f"{number - 1:040x}",) if number else ())
            for number in range(100, -1, -1)
        ]
        backend = FakeHistoryBackend(commits)
        query = HistoryQuery(limit=100, offset=0)

        page = HistoryService(backend).load("repo", query)

        self.assertEqual(len(page.commits), 100)
        self.assertTrue(page.has_more)
        self.assertIsNotNone(page.next_query)
        self.assertEqual(page.next_query.offset, 100)

    def test_load_accepts_parser_records_via_commit_info_conversion(self):
        parsed = ParsedHistoryCommit(
            hash="a" * 40,
            parent_hashes=(),
            author_name="Ada",
            author_email="ada@example.com",
            date="2026-07-20T10:00:00Z",
            message="Structured",
            description="Body",
        )

        page = HistoryService(FakeHistoryBackend([parsed])).load("repo")

        self.assertIsInstance(page.commits[0].info, CommitInfo)
        self.assertEqual(page.commits[0].message, "Structured")
        self.assertEqual(page.commits[0].description, "Body")

    def test_query_hides_remote_and_tag_badges(self):
        item = commit(
            "a" * 40,
            decorations="HEAD -> main, origin/main, tag: release",
        )
        query = HistoryQuery(show_remotes=False, show_tags=False)

        page = HistoryService(FakeHistoryBackend([item])).load("repo", query)

        self.assertEqual(
            [(reference.name, reference.kind) for reference in page.commits[0].references],
            [
                ("HEAD", CommitReferenceKind.HEAD),
                ("main", CommitReferenceKind.LOCAL_BRANCH),
            ],
        )

    def test_filter_searches_all_required_fields_and_recalculates_lanes(self):
        commits = [
            commit(
                "f" * 40,
                ("a" * 40, "b" * 40),
                subject="Merge materials",
                body="Lighting pass",
            ),
            commit(
                "a" * 40,
                author="Ada Lovelace",
                email="ada@example.com",
                subject="Principal",
            ),
            commit("b" * 40, subject="Side"),
        ]
        page = HistoryService(FakeHistoryBackend(commits)).load("repo")

        by_body = filter_history_page(page, "lighting")
        by_author = HistoryService(FakeHistoryBackend([])).filter(page, "ADA@EXAMPLE")
        by_hash = filter_history_page(page, "bbbbbbbb")

        self.assertEqual([item.hash for item in by_body.commits], ["f" * 40])
        self.assertEqual(by_body.commits[0].lane_index, 0)
        self.assertEqual(by_body.commits[0].parent_lane_indexes, (0, 1))
        self.assertEqual([item.hash for item in by_author.commits], ["a" * 40])
        self.assertEqual(by_author.commits[0].lane_index, 0)
        self.assertEqual([item.hash for item in by_hash.commits], ["b" * 40])
        self.assertEqual(by_hash.commits[0].lane_index, 0)

    def test_filter_empty_search_still_rebuilds_a_page(self):
        page = HistoryService(FakeHistoryBackend([commit("A")])).load("repo")
        filtered = filter_history_page(page, "  ")

        self.assertEqual(filtered.commits, page.commits)
        self.assertIsNot(filtered, page)

    def test_load_details_delegates_and_validates_exact_hash(self):
        info = commit("d" * 40, ("c" * 40,), subject="Detailed", body="Description")
        details = CommitDetails(
            commit=info,
            references=(CommitReference("main", CommitReferenceKind.LOCAL_BRANCH),),
            files=(
                CommitFileStat("scene.blend", additions=None, deletions=None, status="M"),
                CommitFileStat("notes.txt", additions=10, deletions=3, status="A"),
            ),
        )
        backend = FakeHistoryBackend([], details)

        loaded = HistoryService(backend).load_details("repo", "d" * 40)

        self.assertIs(loaded, details)
        self.assertEqual(backend.detail_calls, [(Path("repo"), "d" * 40)])
        self.assertEqual(loaded.changed_files, 2)
        self.assertEqual(loaded.total_additions, 10)
        self.assertEqual(loaded.total_deletions, 3)
        self.assertTrue(loaded.files[0].is_binary)

    def test_load_details_rejects_empty_or_mismatched_hash(self):
        details = CommitDetails(commit=commit("a" * 40))
        service = HistoryService(FakeHistoryBackend([], details))

        with self.assertRaisesRegex(ValueError, "required"):
            service.load_details("repo", " ")
        with self.assertRaisesRegex(ValueError, "returned details"):
            service.load_details("repo", "b" * 40)

    def test_rejects_unstructured_backend_values(self):
        service = HistoryService(FakeHistoryBackend([object()]))  # type: ignore[list-item]

        with self.assertRaisesRegex(TypeError, "CommitInfo-compatible"):
            service.load("repo")


if __name__ == "__main__":
    unittest.main()
