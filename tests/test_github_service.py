from __future__ import annotations

import unittest
from unittest.mock import Mock

from blender_git_manager.models import CommandResult
from blender_git_manager.services.git_service import GitCommandError
from blender_git_manager.services.github_service import (
    GitHubService,
    find_github_device_code,
    find_github_device_login_url,
)
from blender_git_manager.services.process_service import ProcessService


class GitHubServiceTests(unittest.TestCase):
    def test_login_web_uses_non_interactive_browser_flow(self):
        process = Mock(spec=ProcessService)
        expected_result = CommandResult(
            executable="gh",
            arguments=(),
            return_code=0,
            stdout="authenticated",
        )
        process.run.return_value = expected_result

        result = GitHubService(executable="custom-gh", process=process).login_web()

        self.assertIs(result, expected_result)
        process.run.assert_called_once()
        positional = process.run.call_args.args
        keywords = process.run.call_args.kwargs
        self.assertEqual(positional[0], "custom-gh")
        self.assertEqual(
            positional[1],
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
        )
        timeout = keywords.get("timeout", positional[3] if len(positional) > 3 else None)
        environment = keywords.get("environment", positional[4] if len(positional) > 4 else None)
        self.assertEqual(timeout, 900)
        self.assertIsNotNone(environment)
        for name in ("GH_PROMPT_DISABLED", "GH_SPINNER_DISABLED", "NO_COLOR"):
            with self.subTest(environment_variable=name):
                self.assertEqual(environment.get(name), "1")

    def test_login_web_redacts_failure_message(self):
        process = Mock(spec=ProcessService)
        secret = "ghp_BGM_GITHUB_ERROR_SENTINEL_123456789"
        process.run.return_value = CommandResult(
            executable="gh",
            arguments=(),
            return_code=1,
            stderr=f"Authorization: Bearer {secret}",
        )

        with self.assertRaises(GitCommandError) as raised:
            GitHubService(process=process).login_web()

        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("***", str(raised.exception))


class FindGitHubDeviceLoginUrlTests(unittest.TestCase):
    def test_finds_device_login_url_in_cli_output(self):
        text = "Open this URL to continue in your web browser: https://github.com/login/device"
        self.assertEqual(find_github_device_login_url(text), "https://github.com/login/device")

    def test_finds_url_surrounded_by_ansi_formatting(self):
        text = "\x1b[1mOpen this URL:\x1b[0m \x1b[36mhttps://github.com/login/device\x1b[0m"
        self.assertEqual(find_github_device_login_url(text), "https://github.com/login/device")

    def test_rejects_unsafe_or_lookalike_urls(self):
        for text in (
            "http://github.com/login/device",
            "https://github.com.evil.example/login/device",
            "https://github.com/login/device/extra",
            "https://github.com@evil.example/login/device",
            "no browser URL here",
        ):
            with self.subTest(text=text):
                self.assertEqual(find_github_device_login_url(text), "")


class FindGitHubDeviceCodeTests(unittest.TestCase):
    def test_finds_code_in_current_cli_clipboard_message(self):
        text = "! One-time code (ABCD-EFGH) copied to clipboard"
        self.assertEqual(find_github_device_code(text), "ABCD-EFGH")

    def test_finds_code_in_copy_instruction(self):
        text = "First copy your one-time code: 1A2B-3C4D"
        self.assertEqual(find_github_device_code(text), "1A2B-3C4D")

    def test_strips_ansi_and_normalizes_code_to_uppercase(self):
        text = "\x1b[33m! One-time code (\x1b[1mabcd-efgh\x1b[0m) copied to clipboard"
        self.assertEqual(find_github_device_code(text), "ABCD-EFGH")

    def test_rejects_unlabeled_redacted_or_malformed_codes(self):
        for text in (
            "Unrelated identifier ABCD-EFGH",
            "! One-time code (***-****) copied to clipboard",
            "! One-time code (ABCDE-FGHI) copied to clipboard",
            "! One-time code (ABCD_EFGH) copied to clipboard",
            "No device code here",
        ):
            with self.subTest(text=text):
                self.assertEqual(find_github_device_code(text), "")
