from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from ..utils.formatting import redact_text, strip_ansi
from .git_service import GitCommandError
from .process_service import ProcessService

GITHUB_DEVICE_LOGIN_URL = "https://github.com/login/device"
_GITHUB_URL_RE = re.compile(r"https://github\.com/[^\s\x1b]+", re.IGNORECASE)
_DEVICE_CODE_RE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", re.IGNORECASE)


def find_github_device_login_url(text: str) -> str:
    """Return only the allow-listed GitHub device URL found in CLI output."""
    for match in _GITHUB_URL_RE.finditer(strip_ansi(text)):
        candidate = match.group(0).rstrip(".,);]}>\"'")
        parsed = urlsplit(candidate)
        if parsed.scheme.lower() == "https" and parsed.hostname == "github.com" and parsed.path == "/login/device":
            return candidate
    return ""


def find_github_device_code(text: str) -> str:
    """Extract the transient device code only from GitHub CLI's labeled message."""
    clean = strip_ansi(text)
    if "one-time code" not in clean.lower():
        return ""
    match = _DEVICE_CODE_RE.search(clean)
    return match.group(0).upper() if match else ""


class GitHubService:
    def __init__(self, executable: str = "gh", process: ProcessService | None = None) -> None:
        self.executable = executable
        self.process = process or ProcessService(default_timeout=300)

    def _run(
        self,
        arguments: list[str],
        cwd: str | Path | None = None,
        timeout: int | None = None,
        environment: dict[str, str] | None = None,
    ):
        return self.process.run(self.executable, arguments, cwd, timeout, environment)

    def _run_checked(self, arguments: list[str], cwd: str | Path | None = None, timeout: int | None = None):
        result = self._run(arguments, cwd, timeout)
        if not result.successful:
            raise GitCommandError(result.stderr or result.stdout or "GitHub CLI command failed.")
        return result

    def version(self):
        return self._run(["--version"], timeout=15)

    def auth_status(self):
        return self._run(["auth", "status", "--hostname", "github.com"], timeout=30)

    def authenticated_user(self) -> str:
        if not self.auth_status().successful:
            return ""
        result = self._run(["api", "user", "--jq", ".login"], timeout=30)
        return result.stdout.strip() if result.successful else ""

    def login_web(self):
        result = self._run(
            [
                "auth",
                "login",
                "--hostname",
                "github.com",
                "--git-protocol",
                "https",
                "--web",
                "--clipboard",
            ],
            timeout=900,
            environment={
                "GH_PROMPT_DISABLED": "1",
                "GH_SPINNER_DISABLED": "1",
                "GH_NO_UPDATE_NOTIFIER": "1",
                "NO_COLOR": "1",
                "CLICOLOR": "0",
            },
        )
        if not result.successful:
            message = redact_text(result.stderr or result.stdout or "GitHub CLI authentication failed.")
            raise GitCommandError(message)
        return result

    def logout(self, username: str = ""):
        arguments = ["auth", "logout", "--hostname", "github.com"]
        if username:
            arguments.extend(["--user", username])
        return self._run_checked(arguments, timeout=120)

    def create_repository(
        self,
        cwd: str | Path,
        name: str,
        visibility: str = "private",
        description: str = "",
        owner: str = "",
        remote_name: str = "origin",
        push: bool = True,
    ):
        repository = f"{owner}/{name}" if owner else name
        arguments = ["repo", "create", repository]
        arguments.append("--public" if visibility == "public" else "--private")
        arguments.extend(["--source", ".", "--remote", remote_name])
        if description.strip():
            arguments.extend(["--description", description.strip()])
        if push:
            arguments.append("--push")
        return self._run_checked(arguments, cwd, timeout=1800)

    def clone_repository(self, repository: str, destination: str | Path):
        return self._run_checked(["repo", "clone", repository, str(destination)], timeout=1800)

    def repository_url(self, cwd: str | Path) -> str:
        result = self._run(["repo", "view", "--json", "url", "--jq", ".url"], cwd, timeout=30)
        return result.stdout.strip() if result.successful else ""

    def auth_status_json(self) -> dict:
        result = self._run(["auth", "status", "--json", "hosts"], timeout=30)
        if not result.successful:
            return {}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
