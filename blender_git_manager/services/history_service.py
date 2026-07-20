"""Application service for loading, laying out and filtering Git History.

The service is pure Python.  A concrete Git implementation is injected via
``HistoryBackend`` so Git processes may run in the add-on's background task
service without exposing Blender APIs to worker threads.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..models import (
    CommitDetails,
    CommitInfo,
    CommitReference,
    CommitReferenceKind,
    HistoryCommit,
    HistoryPage,
    HistoryQuery,
)
from .graph_layout_service import GraphLayoutService


@runtime_checkable
class HistoryBackend(Protocol):
    """Operations a concrete Git backend must provide to ``HistoryService``.

    ``history_graph`` returns commits in newest-to-oldest topological order.
    The service passes ``query.limit + 1`` as ``max_count``; that final
    sentinel commit lets it compute ``HistoryPage.has_more`` without coupling
    pagination logic to Git's textual output.
    """

    def history_graph(
        self,
        cwd: str | Path,
        query: HistoryQuery,
        max_count: int,
    ) -> Sequence[CommitInfo]:
        """Return at most ``max_count`` structured commits for ``query``."""

        ...

    def commit_details(self, cwd: str | Path, full_hash: str) -> CommitDetails:
        """Return complete metadata and file statistics for one exact commit."""

        ...


def parse_commit_references(decorations: str) -> tuple[CommitReference, ...]:
    """Convert Git ``%D`` decorations to semantic, de-duplicated references."""

    if not decorations:
        return ()

    references: list[CommitReference] = []
    seen: set[tuple[str, CommitReferenceKind, str]] = set()

    def append(name: str, kind: CommitReferenceKind, target: str = "") -> None:
        normalized_name = _strip_ref_prefix(name.strip())
        normalized_target = _strip_ref_prefix(target.strip())
        if not normalized_name:
            return
        key = (normalized_name, kind, normalized_target)
        if key in seen:
            return
        seen.add(key)
        references.append(CommitReference(normalized_name, kind, normalized_target))

    for raw_decoration in decorations.split(","):
        decoration = raw_decoration.strip()
        if not decoration:
            continue

        source, separator, target = decoration.partition(" -> ")
        if separator:
            source_kind = _reference_kind(source)
            append(source, source_kind, target)
            # Retain the pointed-to branch as an independently filterable and
            # drawable badge.  HEAD's target is known to be a local branch.
            target_kind = (
                CommitReferenceKind.LOCAL_BRANCH
                if _strip_ref_prefix(source) == "HEAD"
                else _reference_kind(target)
            )
            append(target, target_kind)
            continue

        append(decoration, _reference_kind(decoration))

    return tuple(references)


def filter_history_page(
    page: HistoryPage,
    search: str = "",
    author: str = "",
) -> HistoryPage:
    """Pure case-insensitive filter that recomputes graph lanes.

    Searchable fields are message/body, author name/email and full/short hash.
    ``has_more`` is preserved because filtering an already-loaded page does
    not change whether the backend has another unrequested page.
    """

    needle = search.strip().casefold()
    author_needle = author.strip().casefold()
    selected = tuple(
        commit.info
        for commit in page.commits
        if (not needle or _commit_matches(commit.info, needle))
        and (
            not author_needle
            or author_needle in commit.info.author_name.casefold()
            or author_needle in commit.info.author_email.casefold()
        )
    )

    return _build_page(
        selected,
        query=page.query,
        has_more=page.has_more,
        layout_service=GraphLayoutService(),
    )


class HistoryService:
    """Coordinate a structured History backend and deterministic graph layout."""

    def __init__(
        self,
        backend: HistoryBackend,
        *,
        layout_service: GraphLayoutService | None = None,
    ) -> None:
        self._backend = backend
        self._layout = layout_service or GraphLayoutService()

    def load(
        self,
        cwd: str | Path,
        query: HistoryQuery | None = None,
    ) -> HistoryPage:
        """Load and lay out one page without interacting with Blender."""

        effective_query = query or HistoryQuery()
        raw_commits = self._backend.history_graph(
            cwd,
            effective_query,
            effective_query.limit + 1,
        )
        commits = tuple(_coerce_commit_info(commit) for commit in raw_commits)
        has_more = len(commits) > effective_query.limit
        visible_commits = commits[: effective_query.limit]
        return _build_page(
            visible_commits,
            query=effective_query,
            has_more=has_more,
            layout_service=self._layout,
        )

    def filter(
        self,
        page: HistoryPage,
        search: str = "",
        author: str = "",
    ) -> HistoryPage:
        """Filter a loaded page and recalculate its graph."""

        return filter_history_page(page, search, author)

    def load_details(self, cwd: str | Path, full_hash: str) -> CommitDetails:
        """Load details for one exact commit and verify backend provenance."""

        requested_hash = full_hash.strip()
        if not requested_hash:
            raise ValueError("A full commit hash is required.")

        details = self._backend.commit_details(cwd, requested_hash)
        if not isinstance(details, CommitDetails):
            raise TypeError("History backend commit_details() must return CommitDetails.")
        if details.full_hash != requested_hash:
            raise ValueError(
                "History backend returned details for "
                f"{details.full_hash!r}, expected {requested_hash!r}."
            )
        return details


def _build_page(
    commits: tuple[CommitInfo, ...],
    *,
    query: HistoryQuery,
    has_more: bool,
    layout_service: GraphLayoutService,
) -> HistoryPage:
    rows = layout_service.layout(commits)
    graph_commits = tuple(
        HistoryCommit(
            info=commit,
            references=_visible_references(
                parse_commit_references(commit.decorations),
                query=query,
            ),
            lane_index=row.lane_index,
            parent_lane_indexes=row.parent_lane_indexes,
            lanes_before=row.lanes_before,
            lanes_after=row.lanes_after,
        )
        for commit, row in zip(commits, rows, strict=True)
    )
    return HistoryPage(commits=graph_commits, query=query, has_more=has_more)


def _visible_references(
    references: tuple[CommitReference, ...],
    *,
    query: HistoryQuery,
) -> tuple[CommitReference, ...]:
    return tuple(
        reference
        for reference in references
        if (query.show_remotes or reference.kind is not CommitReferenceKind.REMOTE_BRANCH)
        and (query.show_tags or reference.kind is not CommitReferenceKind.TAG)
    )


def _coerce_commit_info(commit: object) -> CommitInfo:
    if isinstance(commit, CommitInfo):
        return commit
    converter = getattr(commit, "to_commit_info", None)
    if callable(converter):
        converted = converter()
        if isinstance(converted, CommitInfo):
            return converted
    raise TypeError("History backend must return CommitInfo-compatible structured commits.")


def _commit_matches(commit: CommitInfo, needle: str) -> bool:
    searchable = (
        commit.full_hash,
        commit.short_hash,
        commit.subject,
        commit.body,
        commit.author_name,
        commit.author_email,
    )
    return any(needle in value.casefold() for value in searchable)


def _strip_ref_prefix(reference: str) -> str:
    value = reference.strip()
    if value.startswith("tag: "):
        value = value[5:].strip()
    for prefix in ("refs/heads/", "refs/remotes/", "refs/tags/"):
        if value.startswith(prefix):
            return value[len(prefix) :].strip()
    return value


def _reference_kind(reference: str) -> CommitReferenceKind:
    value = reference.strip()
    normalized = _strip_ref_prefix(value)
    if normalized == "HEAD":
        return CommitReferenceKind.HEAD
    if value.startswith(("tag: ", "refs/tags/")):
        return CommitReferenceKind.TAG
    if value.startswith("refs/heads/"):
        return CommitReferenceKind.LOCAL_BRANCH
    if value.startswith("refs/remotes/"):
        return CommitReferenceKind.REMOTE_BRANCH
    if value.startswith("refs/"):
        return CommitReferenceKind.OTHER
    if "/" in normalized:
        # Git's default %D shortening emits remote refs as ``origin/main``.
        # A fully-qualified local branch is handled by the explicit case
        # above; ambiguous shortened slash names stay conservatively remote.
        return CommitReferenceKind.REMOTE_BRANCH
    if normalized:
        return CommitReferenceKind.LOCAL_BRANCH
    return CommitReferenceKind.OTHER
