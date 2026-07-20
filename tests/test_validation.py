from __future__ import annotations

import unittest

from blender_git_manager.utils.validation import (
    ValidationError,
    validate_branch_name,
    validate_commit_message,
    validate_email,
    validate_remote_url,
    validate_repository_name,
    validate_tag_name,
)


class ValidationTests(unittest.TestCase):
    def test_valid_branch(self):
        self.assertEqual(validate_branch_name("feature/materials"), "feature/materials")

    def test_invalid_branch_sequences(self):
        for value in ("", "-main", "main..test", "main.lock", "bad branch", "bad~branch"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_branch_name(value)

    def test_repository_name(self):
        self.assertEqual(validate_repository_name("Tank-Assets_01"), "Tank-Assets_01")
        with self.assertRaises(ValidationError):
            validate_repository_name("Tank Assets")

    def test_remote_url_rejects_embedded_credentials(self):
        self.assertEqual(
            validate_remote_url(" https://github.com/octo/assets.git "),
            "https://github.com/octo/assets.git",
        )
        self.assertEqual(
            validate_remote_url("git@github.com:octo/assets.git"),
            "git@github.com:octo/assets.git",
        )
        self.assertEqual(
            validate_remote_url("ssh://git@github.com/octo/assets.git"),
            "ssh://git@github.com/octo/assets.git",
        )
        for value in (
            "https://user:token@github.com/octo/assets.git",
            "https://user@github.com/octo/assets.git",
            "https://github.com/octo/assets.git?token=secret",
            "https://github.com/octo/assets.git#token=secret",
            "ssh://git:secret@github.com/octo/assets.git",
            "https://[malformed/repository.git",
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_remote_url(value)

    def test_commit_message(self):
        self.assertEqual(validate_commit_message(" Initial commit "), "Initial commit")
        with self.assertRaises(ValidationError):
            validate_commit_message("   ")

    def test_email(self):
        self.assertEqual(validate_email("david@example.com"), "david@example.com")
        with self.assertRaises(ValidationError):
            validate_email("invalid-email")

    def test_tag(self):
        self.assertEqual(validate_tag_name("v1.0.0"), "v1.0.0")
