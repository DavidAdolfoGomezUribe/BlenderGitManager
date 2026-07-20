"""Pure parser for NUL-delimited commit file details produced by Git.

The two supported commands intentionally use ``-z`` so paths are never quoted
or split on whitespace::

    git diff --numstat -z --find-renames <parent> <commit>
    git diff --name-status -z --find-renames <parent> <commit>

Their machine formats are related, but not identical:

``--numstat -z``
    A normal file is ``ADDED<TAB>DELETED<TAB>PATH<NUL>``.  A rename or copy is
    ``ADDED<TAB>DELETED<TAB><NUL>OLD_PATH<NUL>NEW_PATH<NUL>``.  Binary files
    use ``-`` for both counts.  The empty path in the first field is Git's
    unambiguous signal that two path fields follow.

``--name-status -z``
    A normal file is ``STATUS<NUL>PATH<NUL>``.  Renames and copies are
    ``R<score><NUL>OLD_PATH<NUL>NEW_PATH<NUL>`` and
    ``C<score><NUL>OLD_PATH<NUL>NEW_PATH<NUL>``.

Because NUL cannot occur in a Git path, spaces, tabs, Unicode and line breaks
are all preserved without interpreting Git's human-oriented quoting rules.
This module has no Blender dependency and is safe to use in a worker thread.
"""

from __future__ import annotations

from dataclasses import dataclass

DiffOutput = str | bytes


class HistoryDiffParseError(ValueError):
    """Raised when Git output is truncated, malformed or internally mismatched."""


@dataclass(frozen=True, slots=True)
class NumstatRecord:
    """Line statistics and paths for one entry in ``git diff --numstat -z``."""

    path: str
    added_lines: int | None
    deleted_lines: int | None
    old_path: str | None = None

    @property
    def is_binary(self) -> bool:
        return self.added_lines is None and self.deleted_lines is None

    @property
    def original_path(self) -> str:
        """Compatibility name matching the add-on's existing file model."""

        return self.old_path or ""


@dataclass(frozen=True, slots=True)
class NameStatusRecord:
    """Status, optional similarity score and paths for one changed file."""

    status: str
    path: str
    old_path: str | None = None
    similarity: int | None = None

    @property
    def status_token(self) -> str:
        return f"{self.status}{self.similarity:03d}" if self.similarity is not None else self.status

    @property
    def original_path(self) -> str:
        return self.old_path or ""

    @property
    def is_rename(self) -> bool:
        return self.status == "R"

    @property
    def is_copy(self) -> bool:
        return self.status == "C"


@dataclass(frozen=True, slots=True)
class CommitFileRecord:
    """Combined status and line statistics for a commit file entry."""

    status: str
    path: str
    added_lines: int | None
    deleted_lines: int | None
    old_path: str | None = None
    similarity: int | None = None

    @property
    def is_binary(self) -> bool:
        return self.added_lines is None and self.deleted_lines is None

    @property
    def original_path(self) -> str:
        return self.old_path or ""

    @property
    def status_token(self) -> str:
        return f"{self.status}{self.similarity:03d}" if self.similarity is not None else self.status


def _decode_output(output: DiffOutput, command_name: str) -> str:
    if isinstance(output, bytes):
        # Git paths are byte sequences on platforms that allow non-UTF-8
        # filenames.  surrogateescape makes the conversion lossless while
        # preserving normal UTF-8 names as ordinary Python text.
        return output.decode("utf-8", errors="surrogateescape")
    if isinstance(output, str):
        return output
    raise TypeError(f"{command_name} output must be str or bytes, got {type(output).__name__}.")


def _nul_fields(output: DiffOutput, command_name: str) -> list[str]:
    text = _decode_output(output, command_name)
    if not text:
        return []
    if not text.endswith("\0"):
        raise HistoryDiffParseError(f"{command_name} output is truncated: missing final NUL.")
    return text[:-1].split("\0")


def _parse_count(added: str, deleted: str, record_index: int) -> tuple[int | None, int | None]:
    if added == "-" or deleted == "-":
        if added == deleted == "-":
            return None, None
        raise HistoryDiffParseError(
            f"numstat record {record_index} mixes binary and numeric line counts."
        )
    if not added or not deleted or not added.isascii() or not deleted.isascii():
        raise HistoryDiffParseError(f"numstat record {record_index} has invalid line counts.")
    if not added.isdecimal() or not deleted.isdecimal():
        raise HistoryDiffParseError(f"numstat record {record_index} has invalid line counts.")
    return int(added), int(deleted)


def parse_numstat_z(output: DiffOutput) -> list[NumstatRecord]:
    """Parse exact output from ``git diff --numstat -z``.

    The return order is Git's order and can be paired with
    :func:`parse_name_status_z`.  Malformed or incomplete output raises
    :class:`HistoryDiffParseError`; partial results are never returned.
    """

    fields = _nul_fields(output, "numstat")
    records: list[NumstatRecord] = []
    field_index = 0

    while field_index < len(fields):
        header = fields[field_index]
        field_index += 1
        parts = header.split("\t", 2)
        record_index = len(records)
        if len(parts) != 3:
            raise HistoryDiffParseError(
                f"numstat record {record_index} is missing its tab-delimited fields."
            )

        added_text, deleted_text, path = parts
        added_lines, deleted_lines = _parse_count(added_text, deleted_text, record_index)
        old_path: str | None = None

        if not path:
            if field_index + 1 >= len(fields):
                raise HistoryDiffParseError(
                    f"numstat record {record_index} is missing rename/copy paths."
                )
            old_path = fields[field_index]
            path = fields[field_index + 1]
            field_index += 2
            if not old_path or not path:
                raise HistoryDiffParseError(
                    f"numstat record {record_index} has an empty rename/copy path."
                )

        records.append(
            NumstatRecord(
                path=path,
                old_path=old_path,
                added_lines=added_lines,
                deleted_lines=deleted_lines,
            )
        )

    return records


def _parse_status_token(token: str, record_index: int) -> tuple[str, int | None]:
    if not token:
        raise HistoryDiffParseError(f"name-status record {record_index} has an empty status.")

    status = token[0]
    score_text = token[1:]
    if status in {"R", "C"}:
        if (
            not score_text
            or len(score_text) > 3
            or not score_text.isascii()
            or not score_text.isdecimal()
        ):
            raise HistoryDiffParseError(
                f"name-status record {record_index} has an invalid rename/copy score."
            )
        score = int(score_text)
        if not 0 <= score <= 100:
            raise HistoryDiffParseError(
                f"name-status record {record_index} has a score outside 0..100."
            )
        return status, score

    if status not in {"A", "D", "M", "T", "U", "X", "B"} or score_text:
        raise HistoryDiffParseError(
            f"name-status record {record_index} has unsupported status {token!r}."
        )
    return status, None


def parse_name_status_z(output: DiffOutput) -> list[NameStatusRecord]:
    """Parse exact output from ``git diff --name-status -z``."""

    fields = _nul_fields(output, "name-status")
    records: list[NameStatusRecord] = []
    field_index = 0

    while field_index < len(fields):
        record_index = len(records)
        status, similarity = _parse_status_token(fields[field_index], record_index)
        field_index += 1
        path_count = 2 if status in {"R", "C"} else 1
        if field_index + path_count > len(fields):
            raise HistoryDiffParseError(
                f"name-status record {record_index} is missing {path_count} path field(s)."
            )

        old_path: str | None = None
        if path_count == 2:
            old_path = fields[field_index]
            path = fields[field_index + 1]
        else:
            path = fields[field_index]
        field_index += path_count

        if not path or (path_count == 2 and not old_path):
            raise HistoryDiffParseError(
                f"name-status record {record_index} has an empty path."
            )
        records.append(
            NameStatusRecord(
                status=status,
                similarity=similarity,
                path=path,
                old_path=old_path,
            )
        )

    return records


def combine_diff_records(
    numstat_records: list[NumstatRecord],
    name_status_records: list[NameStatusRecord],
) -> list[CommitFileRecord]:
    """Combine equally ordered outputs from the same Git diff invocation.

    Both commands must use identical revisions, pathspecs and rename/copy
    options.  Counts and paths are verified before combining, so a caller
    cannot silently attach statistics to the wrong file.
    """

    if len(numstat_records) != len(name_status_records):
        raise HistoryDiffParseError(
            "numstat and name-status contain a different number of records."
        )

    combined: list[CommitFileRecord] = []
    for index, (numstat, status) in enumerate(zip(numstat_records, name_status_records, strict=True)):
        if numstat.path != status.path or numstat.old_path != status.old_path:
            raise HistoryDiffParseError(
                f"numstat and name-status paths differ at record {index}."
            )
        combined.append(
            CommitFileRecord(
                status=status.status,
                similarity=status.similarity,
                path=status.path,
                old_path=status.old_path,
                added_lines=numstat.added_lines,
                deleted_lines=numstat.deleted_lines,
            )
        )
    return combined


def parse_commit_diff_z(
    numstat_output: DiffOutput,
    name_status_output: DiffOutput,
) -> list[CommitFileRecord]:
    """Parse and safely combine the two NUL-delimited Git diff outputs."""

    return combine_diff_records(
        parse_numstat_z(numstat_output),
        parse_name_status_z(name_status_output),
    )
