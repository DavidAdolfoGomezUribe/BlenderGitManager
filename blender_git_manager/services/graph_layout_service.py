"""Deterministic lane assignment for a Git commit graph.

The service is intentionally independent from Blender and from the concrete
history model.  It consumes commit-like objects in newest-to-oldest
topological order and returns immutable layout rows instead of mutating the
input objects.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar


class GraphCommit(Protocol):
    """Minimum shape accepted by :class:`GraphLayoutService`.

    Existing models expose ``full_hash``.  Models that expose ``hash`` instead
    are also accepted at runtime so the graph service can be reused by a
    dedicated history model.
    """

    full_hash: str
    parent_hashes: Sequence[str]


@dataclass(frozen=True, slots=True)
class GraphLayoutRow:
    """Lane information for one commit row.

    ``lanes_before`` contains the active lane tips at the commit row.
    ``lanes_after`` contains the parents that continue below it.  Empty slots
    are kept as ``None`` while a lane to their right is still active, which
    prevents unrelated lines from jumping horizontally between rows.
    """

    commit_hash: str
    lane_index: int
    parent_lane_indexes: tuple[int, ...]
    lanes_before: tuple[str | None, ...]
    lanes_after: tuple[str | None, ...]

    @property
    def lane_count(self) -> int:
        """Maximum graph width needed to draw this row and its outgoing edges."""

        return max(len(self.lanes_before), len(self.lanes_after))


@dataclass(frozen=True, slots=True)
class _CommitRecord:
    commit_hash: str
    parent_hashes: tuple[str, ...]


CommitT = TypeVar("CommitT")


class GraphLayoutService:
    """Assign stable, reusable lanes to a topologically ordered history."""

    def layout(self, commits: Iterable[CommitT]) -> tuple[GraphLayoutRow, ...]:
        """Return graph rows for commits ordered from newest to oldest.

        Included parents must occur after their children.  Parents outside the
        supplied page are allowed; their lanes remain active in the final row
        so pagination can draw the truncated continuation.
        """

        records = tuple(self._record_from_commit(commit) for commit in commits)
        self._validate_topological_order(records)

        lanes: list[str | None] = []
        rows: list[GraphLayoutRow] = []

        for record in records:
            lane_index = self._find_lane(lanes, record.commit_hash)
            if lane_index is None:
                lane_index = self._allocate_lane(lanes, record.commit_hash)

            lanes_before = tuple(lanes)
            lanes[lane_index] = None
            parent_lane_indexes: list[int] = []

            for parent_number, parent_hash in enumerate(record.parent_hashes):
                parent_lane = self._find_lane(lanes, parent_hash)
                if parent_lane is None:
                    if parent_number == 0 and lanes[lane_index] is None:
                        # First-parent continuity keeps the principal line
                        # vertical whenever that parent is not already active.
                        lanes[lane_index] = parent_hash
                        parent_lane = lane_index
                    else:
                        parent_lane = self._allocate_lane(lanes, parent_hash)
                parent_lane_indexes.append(parent_lane)

            self._trim_unused_trailing_lanes(lanes)
            rows.append(
                GraphLayoutRow(
                    commit_hash=record.commit_hash,
                    lane_index=lane_index,
                    parent_lane_indexes=tuple(parent_lane_indexes),
                    lanes_before=lanes_before,
                    lanes_after=tuple(lanes),
                )
            )

        return tuple(rows)

    @staticmethod
    def _record_from_commit(commit: object) -> _CommitRecord:
        commit_hash = getattr(commit, "hash", None)
        if not isinstance(commit_hash, str):
            commit_hash = getattr(commit, "full_hash", None)
        if not isinstance(commit_hash, str) or not commit_hash.strip():
            raise TypeError("Graph commits must expose a non-empty 'hash' or 'full_hash' string.")

        parent_hashes = getattr(commit, "parent_hashes", None)
        if not isinstance(parent_hashes, Sequence) or isinstance(parent_hashes, (str, bytes)):
            raise TypeError("Graph commits must expose 'parent_hashes' as a sequence of strings.")

        normalized_parents: list[str] = []
        for parent_hash in parent_hashes:
            if not isinstance(parent_hash, str) or not parent_hash.strip():
                raise TypeError("Every parent hash must be a non-empty string.")
            normalized_parents.append(parent_hash.strip())

        return _CommitRecord(commit_hash.strip(), tuple(normalized_parents))

    @staticmethod
    def _validate_topological_order(records: tuple[_CommitRecord, ...]) -> None:
        positions: dict[str, int] = {}
        for index, record in enumerate(records):
            if record.commit_hash in positions:
                raise ValueError(f"Duplicate commit in graph input: {record.commit_hash}")
            positions[record.commit_hash] = index

        for child_index, record in enumerate(records):
            for parent_hash in record.parent_hashes:
                parent_index = positions.get(parent_hash)
                if parent_index is not None and parent_index <= child_index:
                    raise ValueError(
                        "Commits must be in newest-to-oldest topological order; "
                        f"parent {parent_hash} precedes child {record.commit_hash}."
                    )

    @staticmethod
    def _find_lane(lanes: list[str | None], commit_hash: str) -> int | None:
        try:
            return lanes.index(commit_hash)
        except ValueError:
            return None

    @staticmethod
    def _allocate_lane(lanes: list[str | None], commit_hash: str) -> int:
        try:
            lane_index = lanes.index(None)
        except ValueError:
            lanes.append(commit_hash)
            return len(lanes) - 1
        lanes[lane_index] = commit_hash
        return lane_index

    @staticmethod
    def _trim_unused_trailing_lanes(lanes: list[str | None]) -> None:
        while lanes and lanes[-1] is None:
            lanes.pop()


def layout_commit_graph(commits: Iterable[CommitT]) -> tuple[GraphLayoutRow, ...]:
    """Convenience wrapper for callers that do not need a service instance."""

    return GraphLayoutService().layout(commits)
