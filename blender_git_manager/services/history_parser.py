from __future__ import annotations

from ..models import CommitInfo

FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"


def parse_git_log(output: str) -> list[CommitInfo]:
    commits: list[CommitInfo] = []
    for raw_record in output.split(RECORD_SEPARATOR):
        record = raw_record.strip("\r\n ")
        if not record:
            continue
        fields = record.split(FIELD_SEPARATOR)
        if len(fields) < 7:
            continue
        full_hash, parents, author, email, authored_at, decorations, subject = fields[:7]
        body = fields[7] if len(fields) > 7 else ""
        commits.append(
            CommitInfo(
                full_hash=full_hash.strip(),
                parent_hashes=tuple(item for item in parents.split() if item),
                author_name=author.strip(),
                author_email=email.strip(),
                authored_at=authored_at.strip(),
                decorations=decorations.strip(),
                subject=subject.strip(),
                body=body.strip(),
            )
        )
    return commits
