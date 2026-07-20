"""Pure-Python parsing for structured ``git log`` output.

The graph/history code deliberately consumes Git's machine-oriented separators
instead of attempting to interpret the presentation produced by
``git log --graph``.  This module has no dependency on Blender and is therefore
safe to use from a background worker.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import CommitInfo

FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"
SHORT_HASH_LENGTH = 8


@dataclass(frozen=True, slots=True)
class ParsedHistoryCommit:
    """Structured commit data returned by :class:`HistoryParser`.

    ``raw_references`` retains Git's complete ``%D`` value.  ``references`` is
    a normalized, de-duplicated sequence suitable for filtering and badges:
    for example ``HEAD -> main, origin/main, tag: v1.0`` becomes
    ``("HEAD", "main", "origin/main", "v1.0")``.
    """

    hash: str
    parent_hashes: tuple[str, ...]
    author_name: str
    author_email: str
    date: str
    message: str
    raw_references: str = ""
    references: tuple[str, ...] = ()
    description: str = ""
    short_hash: str = field(init=False)
    is_merge: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "short_hash", self.hash[:SHORT_HASH_LENGTH])
        object.__setattr__(self, "is_merge", len(self.parent_hashes) > 1)

    # Compatibility aliases make the parsed result easy to adapt to the
    # existing CommitInfo model without duplicating parsing logic.
    @property
    def full_hash(self) -> str:
        return self.hash

    @property
    def authored_at(self) -> str:
        return self.date

    @property
    def subject(self) -> str:
        return self.message

    @property
    def body(self) -> str:
        return self.description

    @property
    def decorations(self) -> str:
        return self.raw_references

    def to_commit_info(self) -> CommitInfo:
        """Convert to the domain model used by the existing add-on code."""

        return CommitInfo(
            full_hash=self.hash,
            parent_hashes=self.parent_hashes,
            author_name=self.author_name,
            author_email=self.author_email,
            authored_at=self.date,
            decorations=self.raw_references,
            subject=self.message,
            body=self.description,
        )


def normalize_references(raw_references: str) -> tuple[str, ...]:
    """Normalize the decoration text emitted by Git's ``%D`` placeholder.

    Git formats decorations as a comma-separated list.  Arrow decorations are
    expanded so both ``HEAD`` and its target branch can be discovered, while
    the display-only ``tag: `` and fully-qualified ref prefixes are removed.
    Ordering is retained and duplicate names are discarded.
    """

    normalized: list[str] = []
    seen: set[str] = set()

    def append(reference: str) -> None:
        name = reference.strip()
        if name.startswith("tag: "):
            name = name.removeprefix("tag: ").strip()
        for prefix in ("refs/heads/", "refs/remotes/", "refs/tags/"):
            if name.startswith(prefix):
                name = name[len(prefix) :].strip()
                break
        if name and name not in seen:
            seen.add(name)
            normalized.append(name)

    for decoration in raw_references.split(","):
        value = decoration.strip()
        if not value:
            continue
        if " -> " in value:
            source, target = value.split(" -> ", 1)
            append(source)
            append(target)
        else:
            append(value)
    return tuple(normalized)


class HistoryParser:
    """Parser for records separated by ASCII US (fields) and RS (commits)."""

    @staticmethod
    def parse(output: str, *, include_body: bool = False) -> list[ParsedHistoryCommit]:
        """Parse structured history output without raising on truncated records.

        The required format contains seven fields::

            %H%x1f%P%x1f%an%x1f%ae%x1f%ad%x1f%D%x1f%s%x1e

        Pass ``include_body=True`` when an eighth ``%b`` field is appended.
        Empty records and records truncated before the subject are ignored.
        Splitting is bounded so delimiter characters in the last field are
        retained instead of causing an index or unpacking failure.
        """

        if not output:
            return []

        commits: list[ParsedHistoryCommit] = []
        expected_fields = 8 if include_body else 7
        max_splits = expected_fields - 1

        for raw_record in output.split(RECORD_SEPARATOR):
            # Git may put a line break between a record separator and the next
            # hash.  Do not strip ordinary spaces from message/body contents.
            record = raw_record.strip("\r\n")
            if not record:
                continue

            fields = record.split(FIELD_SEPARATOR, max_splits)
            if len(fields) < expected_fields:
                # A killed/timed-out Git process can leave a partial final
                # record.  Omitting it is safer than inventing graph metadata.
                continue

            full_hash, parents, author, email, authored_at, decorations, subject = fields[:7]
            full_hash = full_hash.lstrip("\ufeff").strip()
            if not full_hash:
                continue

            body = fields[7] if include_body else ""
            raw_references = decorations.strip()
            parent_hashes = tuple(parent for parent in parents.split() if parent)
            commits.append(
                ParsedHistoryCommit(
                    hash=full_hash,
                    parent_hashes=parent_hashes,
                    author_name=author.strip(),
                    author_email=email.strip(),
                    date=authored_at.strip(),
                    message=subject.strip(),
                    raw_references=raw_references,
                    references=normalize_references(raw_references),
                    description=body.strip(),
                )
            )
        return commits


def parse_history(output: str, *, include_body: bool = False) -> list[ParsedHistoryCommit]:
    """Functional entry point for the graph-oriented structured parser."""

    return HistoryParser.parse(output, include_body=include_body)


def parse_git_log(output: str) -> list[CommitInfo]:
    """Parse the existing eight-field log format into ``CommitInfo`` objects.

    This compatibility wrapper preserves the public API currently consumed by
    :class:`GitService`, while sharing the robust parser with the new graph.
    """

    return [commit.to_commit_info() for commit in parse_history(output, include_body=True)]
