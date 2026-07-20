"""Pure-Python models used by the graph-oriented History view.

These models deliberately avoid importing Blender or a concrete Git backend.
They can therefore cross the background-worker boundary and be consumed by
the UI only after control has returned to Blender's main thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .domain import CommitInfo


MIN_HISTORY_PAGE_SIZE = 100
MAX_HISTORY_PAGE_SIZE = 1000
DEFAULT_HISTORY_PAGE_SIZE = 200


class CommitReferenceKind(str, Enum):
    """Semantic kind of a decoration attached to a commit."""

    HEAD = "HEAD"
    LOCAL_BRANCH = "LOCAL_BRANCH"
    REMOTE_BRANCH = "REMOTE_BRANCH"
    TAG = "TAG"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class CommitReference:
    """One typed Git reference displayed beside a commit.

    ``target`` is primarily useful for symbolic references such as
    ``HEAD -> main`` or ``origin/HEAD -> origin/main``.
    """

    name: str
    kind: CommitReferenceKind
    target: str = ""

    def __post_init__(self) -> None:
        name = self.name.strip()
        target = self.target.strip()
        if not name:
            raise ValueError("Commit reference names cannot be empty.")
        if not isinstance(self.kind, CommitReferenceKind):
            raise TypeError("Commit reference kind must be a CommitReferenceKind.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "target", target)


@dataclass(frozen=True, slots=True)
class HistoryQuery:
    """Selection and pagination options understood by a History backend."""

    limit: int = DEFAULT_HISTORY_PAGE_SIZE
    offset: int = 0
    show_all_branches: bool = True
    show_remotes: bool = True
    show_tags: bool = True
    branch_filter: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("History limit must be an integer.")
        if not MIN_HISTORY_PAGE_SIZE <= self.limit <= MAX_HISTORY_PAGE_SIZE:
            raise ValueError(
                f"History limit must be between {MIN_HISTORY_PAGE_SIZE} "
                f"and {MAX_HISTORY_PAGE_SIZE}."
            )
        if isinstance(self.offset, bool) or not isinstance(self.offset, int):
            raise TypeError("History offset must be an integer.")
        if self.offset < 0:
            raise ValueError("History offset cannot be negative.")
        if not isinstance(self.branch_filter, str):
            raise TypeError("History branch filter must be a string.")
        object.__setattr__(self, "branch_filter", self.branch_filter.strip())

    def next_page(self) -> HistoryQuery:
        """Return a query for the page immediately following this one."""

        return HistoryQuery(
            limit=self.limit,
            offset=self.offset + self.limit,
            show_all_branches=self.show_all_branches,
            show_remotes=self.show_remotes,
            show_tags=self.show_tags,
            branch_filter=self.branch_filter,
        )


@dataclass(frozen=True, slots=True)
class HistoryCommit:
    """Existing :class:`CommitInfo` enriched with graph layout metadata."""

    info: CommitInfo
    references: tuple[CommitReference, ...] = ()
    lane_index: int = 0
    parent_lane_indexes: tuple[int, ...] = ()
    lanes_before: tuple[str | None, ...] = ()
    lanes_after: tuple[str | None, ...] = ()

    @property
    def hash(self) -> str:
        return self.info.full_hash

    @property
    def full_hash(self) -> str:
        """Compatibility alias used by existing History consumers."""

        return self.info.full_hash

    @property
    def short_hash(self) -> str:
        return self.info.short_hash

    @property
    def parent_hashes(self) -> tuple[str, ...]:
        return self.info.parent_hashes

    @property
    def author_name(self) -> str:
        return self.info.author_name

    @property
    def author_email(self) -> str:
        return self.info.author_email

    @property
    def date(self) -> str:
        return self.info.authored_at

    @property
    def authored_at(self) -> str:
        return self.info.authored_at

    @property
    def message(self) -> str:
        return self.info.subject

    @property
    def subject(self) -> str:
        return self.info.subject

    @property
    def description(self) -> str:
        return self.info.body

    @property
    def body(self) -> str:
        return self.info.body

    @property
    def decorations(self) -> str:
        return self.info.decorations

    @property
    def is_merge(self) -> bool:
        return self.info.is_merge

    @property
    def lane_count(self) -> int:
        return max(len(self.lanes_before), len(self.lanes_after), self.lane_index + 1)


@dataclass(frozen=True, slots=True)
class HistoryPage:
    """One laid-out, immutable page of History commits."""

    commits: tuple[HistoryCommit, ...]
    query: HistoryQuery
    has_more: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.commits

    @property
    def next_query(self) -> HistoryQuery | None:
        return self.query.next_page() if self.has_more else None


@dataclass(frozen=True, slots=True)
class CommitFileStat:
    """Per-file statistics for one commit.

    Git represents binary numstat counts with ``-``.  The backend maps those
    values to ``None``, making ``is_binary`` explicit without inventing a
    numeric change count.
    """

    path: str
    additions: int | None = 0
    deletions: int | None = 0
    status: str = ""
    old_path: str = ""

    def __post_init__(self) -> None:
        path = self.path
        if not path or "\x00" in path:
            raise ValueError("Commit file paths cannot be empty.")
        for label, value in (("additions", self.additions), ("deletions", self.deletions)):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"Commit file {label} must be a non-negative integer or None.")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "status", self.status.strip())
        if "\x00" in self.old_path:
            raise ValueError("Commit file paths cannot contain NUL characters.")

    @property
    def is_binary(self) -> bool:
        return self.additions is None or self.deletions is None

    @property
    def total_changes(self) -> int | None:
        if self.is_binary:
            return None
        return int(self.additions) + int(self.deletions)


@dataclass(frozen=True, slots=True)
class CommitDetails:
    """Complete, UI-ready metadata for one selected commit."""

    commit: CommitInfo
    references: tuple[CommitReference, ...] = ()
    files: tuple[CommitFileStat, ...] = ()

    @property
    def hash(self) -> str:
        return self.commit.full_hash

    @property
    def full_hash(self) -> str:
        return self.commit.full_hash

    @property
    def short_hash(self) -> str:
        return self.commit.short_hash

    @property
    def parent_hashes(self) -> tuple[str, ...]:
        return self.commit.parent_hashes

    @property
    def author_name(self) -> str:
        return self.commit.author_name

    @property
    def author_email(self) -> str:
        return self.commit.author_email

    @property
    def date(self) -> str:
        return self.commit.authored_at

    @property
    def message(self) -> str:
        return self.commit.subject

    @property
    def description(self) -> str:
        return self.commit.body

    @property
    def total_additions(self) -> int:
        return sum(item.additions or 0 for item in self.files)

    @property
    def total_deletions(self) -> int:
        return sum(item.deletions or 0 for item in self.files)

    @property
    def changed_files(self) -> int:
        return len(self.files)
