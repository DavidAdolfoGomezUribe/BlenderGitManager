from __future__ import annotations

import unittest
from dataclasses import dataclass

from blender_git_manager.services.graph_layout_service import GraphLayoutService, layout_commit_graph


@dataclass(frozen=True)
class Commit:
    full_hash: str
    parent_hashes: tuple[str, ...] = ()


@dataclass(frozen=True)
class HashNamedCommit:
    hash: str
    parent_hashes: tuple[str, ...] = ()


class GraphLayoutServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GraphLayoutService()

    def test_linear_history_keeps_first_parent_in_same_lane(self):
        rows = self.service.layout(
            (
                Commit("C3", ("C2",)),
                Commit("C2", ("C1",)),
                Commit("C1"),
            )
        )

        self.assertEqual([row.lane_index for row in rows], [0, 0, 0])
        self.assertEqual([row.parent_lane_indexes for row in rows], [(0,), (0,), ()])
        self.assertEqual(rows[-1].lanes_after, ())

    def test_parallel_tips_converge_at_shared_parent(self):
        rows = self.service.layout(
            (
                Commit("MAIN", ("BASE",)),
                Commit("FEATURE", ("BASE",)),
                Commit("BASE"),
            )
        )

        self.assertEqual(rows[0].lane_index, 0)
        self.assertEqual(rows[1].lane_index, 1)
        self.assertEqual(rows[1].parent_lane_indexes, (0,))
        self.assertEqual(rows[2].lane_index, 0)

    def test_merge_creates_parent_lanes_and_joins_them(self):
        rows = self.service.layout(
            (
                Commit("MERGE", ("MAIN", "FEATURE")),
                Commit("MAIN", ("BASE",)),
                Commit("FEATURE", ("BASE",)),
                Commit("BASE"),
            )
        )

        self.assertEqual(rows[0].lane_index, 0)
        self.assertEqual(rows[0].parent_lane_indexes, (0, 1))
        self.assertEqual(rows[0].lanes_after, ("MAIN", "FEATURE"))
        self.assertEqual(rows[2].lane_index, 1)
        self.assertEqual(rows[2].parent_lane_indexes, (0,))

    def test_octopus_merge_supports_all_parents(self):
        rows = self.service.layout(
            (
                Commit("OCTOPUS", ("P1", "P2", "P3")),
                Commit("P1"),
                Commit("P2"),
                Commit("P3"),
            )
        )

        self.assertEqual(rows[0].parent_lane_indexes, (0, 1, 2))
        self.assertEqual(rows[0].lane_count, 3)
        self.assertEqual([row.lane_index for row in rows], [0, 0, 1, 2])

    def test_existing_first_parent_keeps_its_lane(self):
        rows = self.service.layout(
            (
                Commit("OTHER_TIP", ("SHARED",)),
                Commit("MERGE_TIP", ("SHARED", "SIDE")),
                Commit("SHARED"),
                Commit("SIDE"),
            )
        )

        self.assertEqual(rows[1].lane_index, 1)
        self.assertEqual(rows[1].parent_lane_indexes, (0, 1))
        self.assertEqual(rows[1].lanes_after, ("SHARED", "SIDE"))

    def test_finished_lane_is_reused_without_shifting_active_lane(self):
        rows = self.service.layout(
            (
                Commit("TIP_A", ("ROOT_A",)),
                Commit("TIP_B", ("ROOT_B",)),
                Commit("ROOT_A"),
                Commit("TIP_C", ("ROOT_C",)),
                Commit("ROOT_C"),
                Commit("ROOT_B"),
            )
        )

        self.assertEqual(rows[1].lane_index, 1)
        self.assertEqual(rows[2].lanes_after, (None, "ROOT_B"))
        self.assertEqual(rows[3].lane_index, 0)
        self.assertEqual(rows[5].lane_index, 1)

    def test_truncated_history_keeps_missing_parent_lanes_active(self):
        rows = self.service.layout((Commit("MERGE", ("MISSING_MAIN", "MISSING_SIDE")),))

        self.assertEqual(rows[0].parent_lane_indexes, (0, 1))
        self.assertEqual(rows[0].lanes_after, ("MISSING_MAIN", "MISSING_SIDE"))

    def test_hash_named_model_and_convenience_function_are_supported(self):
        rows = layout_commit_graph(
            (
                HashNamedCommit("NEW", ("OLD",)),
                HashNamedCommit("OLD"),
            )
        )

        self.assertEqual([row.commit_hash for row in rows], ["NEW", "OLD"])
        self.assertEqual([row.lane_index for row in rows], [0, 0])

    def test_rejects_duplicate_commits(self):
        with self.assertRaisesRegex(ValueError, "Duplicate commit"):
            self.service.layout((Commit("SAME"), Commit("SAME")))

    def test_rejects_non_topological_order(self):
        with self.assertRaisesRegex(ValueError, "topological order"):
            self.service.layout((Commit("PARENT"), Commit("CHILD", ("PARENT",))))

    def test_rejects_invalid_commit_shape(self):
        with self.assertRaisesRegex(TypeError, "hash"):
            self.service.layout((object(),))


if __name__ == "__main__":
    unittest.main()
