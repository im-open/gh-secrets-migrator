"""
Standalone repro and debug helper for PyGithub IncompletableObject behavior.

This script demonstrates:
1) The old completion-prone filtering pattern that can fail.
2) The current fixed filtering path in src/clients/github.py.

Run with:
  python script/debug_incompletable_object.py

Or run from VS Code using the launch config in .vscode/launch.json.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


# Ensure imports from src/ work regardless of how this script is launched.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


try:
    from github.GithubException import IncompletableObject
except Exception:
    class IncompletableObject(Exception):
        """Fallback for environments without PyGithub installed."""


class ConsoleLogger:
    """Simple logger compatible with GitHubClient's expected logger methods."""

    def debug(self, msg: str) -> None:
        print(f"DEBUG: {msg}")

    def info(self, msg: str) -> None:
        print(f"INFO: {msg}")

    def warn(self, msg: str) -> None:
        print(f"WARN: {msg}")

    def error(self, msg: str) -> None:
        print(f"ERROR: {msg}")

    def success(self, msg: str) -> None:
        print(f"SUCCESS: {msg}")


class CompletionProneSecret:
    """Secret-like object that raises when completion-prone properties are used."""

    def __init__(self, name: str, is_org_secret: bool = False):
        self._rawData = {"name": name}
        if is_org_secret:
            self._rawData["visibility"] = "selected"

    @property
    def raw_data(self) -> dict[str, Any]:
        raise IncompletableObject(400, message="Cannot complete object as it contains no URL")

    @property
    def name(self) -> str:
        raise IncompletableObject(400, message="Cannot complete object as it contains no URL")


class FakeRepo:
    def __init__(self, secrets: list[CompletionProneSecret]):
        self._secrets = secrets

    def get_secrets(self):
        return self._secrets


class FakeGithub:
    def __init__(self, secrets: list[CompletionProneSecret]):
        self._repo = FakeRepo(secrets)

    def get_repo(self, _full_name: str) -> FakeRepo:
        return self._repo


def old_completion_prone_filter(secrets: list[CompletionProneSecret]) -> list[str]:
    """Emulates the old behavior that can trigger lazy completion failures."""
    result: list[str] = []
    for secret in secrets:
        if "visibility" in secret.raw_data:
            print(f"Skipping organization secret: {secret.name}")
            continue
        result.append(secret.name)
    return result


def run_fixed_filter_via_client(secrets: list[CompletionProneSecret]) -> list[str]:
    """Runs the current production path in GitHubClient.list_repo_secrets."""
    from src.clients.github import GitHubClient

    logger = ConsoleLogger()
    client = GitHubClient("fake-token", logger)
    client.client = FakeGithub(secrets)
    return client.list_repo_secrets("demo-org", "demo-repo")


def main() -> None:
    secrets = [
        CompletionProneSecret("REPO_SECRET_1", is_org_secret=False),
        CompletionProneSecret("ORG_SECRET_1", is_org_secret=True),
        CompletionProneSecret("REPO_SECRET_2", is_org_secret=False),
    ]

    print("--- Step 1: Reproduce old completion-prone behavior ---")
    try:
        old_result = old_completion_prone_filter(secrets)
        print(f"Unexpected success with old behavior: {old_result}")
    except Exception as exc:
        print(f"Expected failure observed: {type(exc).__name__}: {exc}")

    print("\n--- Step 2: Run fixed behavior in GitHubClient.list_repo_secrets ---")
    try:
        fixed_result = run_fixed_filter_via_client(secrets)
        print(f"Fixed behavior result: {fixed_result}")
    except Exception as exc:
        print(f"Unexpected failure in fixed path: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
