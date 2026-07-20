from __future__ import annotations

import unittest

from blender_git_manager.utils.formatting import redact_text, strip_url_credentials


class RedactTextTests(unittest.TestCase):
    def assert_redacted(self, text: str, secret: str) -> str:
        redacted = redact_text(text)
        self.assertNotIn(secret, redacted)
        self.assertIn("***", redacted)
        return redacted

    def test_redacts_authorization_bearer_value(self):
        secret = "gho_BGM_BEARER_SENTINEL_123456789"
        redacted = self.assert_redacted(f"Authorization: Bearer {secret}", secret)
        self.assertIn("Authorization", redacted)

    def test_redacts_github_token_families_in_free_text(self):
        for secret in (
            "ghp_BGM_CLASSIC_SENTINEL_123456789",
            "github_pat_BGM_FINE_GRAINED_SENTINEL_123456789",
        ):
            with self.subTest(secret=secret):
                self.assert_redacted(f"remote response included {secret}", secret)

    def test_redacts_key_value_secrets(self):
        for text, secret in (
            ("password=hunter2-test-sentinel", "hunter2-test-sentinel"),
            ("client_secret: oauth-secret-test-sentinel", "oauth-secret-test-sentinel"),
            ("--token=command-line-test-sentinel", "command-line-test-sentinel"),
        ):
            with self.subTest(text=text):
                self.assert_redacted(text, secret)

    def test_redacts_credentials_embedded_in_url(self):
        secret = "url-password-test-sentinel"
        redacted = self.assert_redacted(
            f"https://test-user:{secret}@github.com/owner/repository.git",
            secret,
        )
        self.assertIn("github.com/owner/repository.git", redacted)
        self.assertEqual(
            strip_url_credentials(
                f"https://test-user:{secret}@github.com/owner/repository.git"
            ),
            "https://github.com/owner/repository.git",
        )
        self.assertEqual(
            strip_url_credentials(
                f"ssh://git:{secret}@github.com/owner/repository.git"
            ),
            "ssh://git@github.com/owner/repository.git",
        )
        self.assertEqual(
            strip_url_credentials("ssh://git@github.com/owner/repository.git"),
            "ssh://git@github.com/owner/repository.git",
        )

    def test_redacts_labeled_oauth_device_code(self):
        code = "ABCD-EFGH"
        redacted = self.assert_redacted(f"Copy your one-time code: {code}", code)
        self.assertIn("***-****", redacted)

    def test_preserves_non_sensitive_process_output(self):
        text = "Open this URL to continue: https://github.com/login/device"
        self.assertEqual(redact_text(text), text)
