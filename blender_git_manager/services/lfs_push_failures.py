"""Strict classification of Git LFS failures reported by ``git push``."""

from __future__ import annotations

import re
from enum import Enum
from urllib.parse import urlsplit

from ..models import CommandResult
from ..utils.formatting import strip_ansi

_LOCKSVERIFY_COMMAND = re.compile(
    r"(?i)\bgit\s+config\s+(?P<key>lfs\.\S+?\.locksverify)\s+false(?:\s|$)"
)
_AUTH_HTTP_STATUS = re.compile(r"(?i)\bHTTP(?:/\d(?:\.\d)?)?:?\s+(?:401|403)\b")
_AUTH_STATUS_CODE = re.compile(r"(?i)\bstatus(?:\s+code)?\s*[:=]?\s*(?:401|403)\b")
_TRANSIENT_HTTP_STATUS = re.compile(r"(?i)\bHTTP(?:/\d(?:\.\d)?)?:?\s+(?:500|502|503|504)\b")
_TRANSIENT_STATUS_CODE = re.compile(r"(?i)\bstatus(?:\s+code)?\s*[:=]?\s*(?:500|502|503|504)\b")


class LFSFailureKind(str, Enum):
    NONE = "NONE"
    LOCK_VERIFY = "LOCK_VERIFY"
    TRANSIENT_BATCH = "TRANSIENT_BATCH"


def _combined_output(result: CommandResult) -> str:
    return strip_ansi("\n".join(part for part in (result.stderr, result.stdout) if part))


def extract_github_locksverify_key(value: str) -> str:
    """Return only a safe repository-specific GitHub LFS locksverify key."""
    text = strip_ansi(value)
    for match in _LOCKSVERIFY_COMMAND.finditer(text):
        key = match.group("key")
        endpoint = key[len("lfs.") : -len(".locksverify")]
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme.lower() == "https"
            and (parsed.hostname or "").lower() == "github.com"
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path.endswith("/info/lfs")
        ):
            return key
    return ""


def classify_lfs_push_failure(result: CommandResult) -> LFSFailureKind:
    if result.successful or result.cancelled or result.timed_out:
        return LFSFailureKind.NONE

    text = _combined_output(result)
    lowered = text.lower()
    hard_failure_markers = (
        "authentication failed",
        "authentication required",
        "authorization error",
        "authorization failed",
        "unauthorized",
        "forbidden",
        "access denied",
        "permission denied",
        "repository not found",
        "non-fast-forward",
        "unable to push locked files",
        "locked by",
        "missing object",
        "missing or corrupt local object",
        "lfs bandwidth quota",
        "storage quota",
    )
    if (
        bool(_AUTH_HTTP_STATUS.search(text))
        or bool(_AUTH_STATUS_CODE.search(text))
        or ("git credentials for " in lowered and " not found" in lowered)
        or any(marker in lowered for marker in hard_failure_markers)
    ):
        return LFSFailureKind.NONE

    batch_context = any(
        marker in lowered
        for marker in (
            "batch response:",
            "/info/lfs/objects/batch",
            "tqclient.batch",
        )
    )
    transient_context = (
        bool(_TRANSIENT_HTTP_STATUS.search(text))
        or bool(_TRANSIENT_STATUS_CODE.search(text))
        or "we couldn't respond to your request in time" in lowered
        or "bad gateway" in lowered
        or "service unavailable" in lowered
        or "gateway timeout" in lowered
        or "connection reset" in lowered
        or "tls handshake timeout" in lowered
        or "i/o timeout" in lowered
        or "context deadline exceeded" in lowered
    )
    if batch_context and transient_context:
        return LFSFailureKind.TRANSIENT_BATCH

    lock_context = (
        "does not support the git lfs locking api" in lowered
        or "/locks/verify" in lowered
        or "searchverifiable" in lowered
        or "lockverifier" in lowered
        or "verifylocksforupdates" in lowered
    )
    if lock_context and extract_github_locksverify_key(text):
        return LFSFailureKind.LOCK_VERIFY

    return LFSFailureKind.NONE
