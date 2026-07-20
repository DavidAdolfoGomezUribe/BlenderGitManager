from __future__ import annotations

import re
from collections.abc import Sequence
from urllib.parse import urlsplit, urlunsplit

from ..constants import SENSITIVE_ARGUMENT_MARKERS

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_URL_CREDENTIALS_RE = re.compile(r"(?i)\b(https?://)([^/\s@]+)@")
_GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
_AUTHORIZATION_RE = re.compile(r"(?i)\b(authorization\s*:\s*(?:bearer|token)\s+)([^\s,;]+)")
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]{8,})")
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])([A-Za-z0-9_-]*(?:token|password|passwd|secret|credential)[A-Za-z0-9_-]*)"
    r"(\s*(?::|=)\s*)([^\s,;]+)"
)
_DEVICE_CODE_RE = re.compile(
    r"(?i)((?:one[- ]time code|copy your one[- ]time code)[^A-Z0-9]{0,24})([A-Z0-9]{4}-[A-Z0-9]{4})"
)


def format_bytes(size: int) -> str:
    value = float(max(size, 0))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def strip_ansi(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", str(value))


def strip_url_credentials(value: str) -> str:
    """Remove passwords/userinfo before a remote URL is persisted in Blender state."""
    text = strip_ansi(str(value))
    try:
        parsed = urlsplit(text)
    except ValueError:
        return _URL_CREDENTIALS_RE.sub(r"\1", text)

    if "@" not in parsed.netloc:
        return text

    raw_userinfo, host = parsed.netloc.rsplit("@", 1)
    if parsed.scheme.lower() in {"http", "https"}:
        safe_netloc = host
    elif parsed.password is not None:
        raw_username = raw_userinfo.split(":", 1)[0]
        safe_netloc = f"{raw_username}@{host}" if raw_username else host
    else:
        return text
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path, parsed.query, parsed.fragment))


def redact_text(value: str) -> str:
    """Remove credentials and transient OAuth codes before output is persisted or printed."""
    text = strip_ansi(str(value))
    text = _URL_CREDENTIALS_RE.sub(r"\1***@", text)
    text = _GITHUB_TOKEN_RE.sub("***", text)
    text = _AUTHORIZATION_RE.sub(r"\1***", text)
    text = _BEARER_RE.sub(r"\1***", text)
    text = _SENSITIVE_VALUE_RE.sub(r"\1\2***", text)
    text = _DEVICE_CODE_RE.sub(r"\1***-****", text)
    return text


def redact_arguments(arguments: Sequence[str]) -> list[str]:
    """Redact values that look like credentials before writing command logs."""
    result: list[str] = []
    redact_next = False
    for argument in arguments:
        lowered = argument.lower()
        if redact_next:
            result.append("***")
            redact_next = False
            continue
        if lowered.startswith(("https://", "http://")) and "@" in lowered:
            prefix, suffix = argument.rsplit("@", 1)
            scheme = prefix.split(":", 1)[0]
            result.append(f"{scheme}://***@{suffix}")
            continue
        option_name = lowered.split("=", 1)[0] if argument.startswith("-") else ""
        if option_name and any(marker in option_name for marker in SENSITIVE_ARGUMENT_MARKERS):
            if "=" in argument:
                key, _value = argument.split("=", 1)
                result.append(f"{key}=***")
            else:
                result.append(argument)
                redact_next = True
            continue
        result.append(redact_text(argument))
    return result
