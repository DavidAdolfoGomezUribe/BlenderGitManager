"""Credential policy helpers.

The add-on deliberately delegates secret storage to GitHub CLI, Git Credential
Manager, or SSH agents. No token getter or token persistence API exists here.
"""

from __future__ import annotations


class CredentialService:
    @staticmethod
    def policy_summary() -> str:
        return (
            "Credentials are managed by GitHub CLI, Git Credential Manager, or the system SSH agent. "
            "Blender Git Manager never stores passwords, private keys, or access tokens in .blend files."
        )

    @staticmethod
    def may_log_environment_variable(name: str) -> bool:
        upper = name.upper()
        blocked = ("TOKEN", "PASSWORD", "SECRET", "PRIVATE_KEY", "CREDENTIAL")
        return not any(marker in upper for marker in blocked)
