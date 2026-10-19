# SPDX-License-Identifier: MIT OR Apache-2.0

"""Thin wrapper around the GitHub CLI (``gh``).

Everything here shells out to ``gh`` instead of hitting the REST API directly,
so authentication, proxies and enterprise hosts are handled by the user's
existing ``gh`` configuration.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass

GH_MISSING = (
    "the GitHub CLI ('gh') was not found on PATH. "
    "Install it from https://cli.github.com/ and run 'gh auth login'."
)

NOT_FOUND_MARKERS = ("not found", "branch not found")
UNRELATED_MARKERS = ("no common ancestor",)
TRANSIENT_MARKERS = (
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "gateway timeout",
    "bad gateway",
    "service unavailable",
    "connection reset",
    "timed out",
)

RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY = 2.0


class GhError(RuntimeError):
    """A ``gh`` invocation failed."""


class GhNotFound(GhError):
    """The requested resource or ref does not exist."""


class GhUnrelatedHistory(GhError):
    """The two refs share no common ancestor (rewritten history)."""


def require_gh() -> None:
    if shutil.which("gh") is None:
        raise GhError(GH_MISSING)


def _error_message(stdout: str, stderr: str) -> str:
    """Extract GitHub's own error message.

    ``gh`` writes the human-readable line to stderr and the API's JSON error
    body to stdout, so stdout is searched first: it carries GitHub's wording,
    which is more precise than the ``gh: ... (HTTP 404)`` summary.
    """
    for stream in (stdout, stderr):
        for line in stream.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = payload.get("message")
                if message:
                    return str(message)
    return (stderr or stdout).strip()


def _run_once(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run(args: list[str], timeout: int = 60) -> str:
    """Run ``gh`` and return stdout, retrying transient API failures.

    Auditing a large account issues hundreds of calls, and GitHub answers a
    fraction of them with a 502 or a 504. A retry with backoff turns those
    into a slightly slower run instead of a failed one.
    """
    delay = RETRY_BASE_DELAY
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            proc = _run_once(args, timeout)
        except subprocess.TimeoutExpired as exc:
            if attempt == RETRY_ATTEMPTS:
                raise GhError(f"gh {' '.join(args)} timed out after {timeout}s") from exc
            time.sleep(delay)
            delay *= 2
            continue

        if proc.returncode == 0:
            return proc.stdout

        message = _error_message(proc.stdout or "", proc.stderr or "")
        lowered = message.lower()
        if any(marker in lowered for marker in UNRELATED_MARKERS):
            raise GhUnrelatedHistory(message)
        if any(marker in lowered for marker in NOT_FOUND_MARKERS):
            raise GhNotFound(message)
        transient = any(marker in lowered for marker in TRANSIENT_MARKERS)
        if transient and attempt < RETRY_ATTEMPTS:
            time.sleep(delay)
            delay *= 2
            continue
        raise GhError(message or f"gh {' '.join(args)} failed with code {proc.returncode}")
    raise GhError(f"gh {' '.join(args)} failed after {RETRY_ATTEMPTS} attempts")


def api_json(endpoint: str, timeout: int = 60):
    """Call a GitHub REST endpoint and decode the JSON body."""
    out = _run(["api", endpoint], timeout=timeout)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise GhError(f"gh api {endpoint}: response was not valid JSON") from exc


def api_jq(endpoint: str, expression: str, timeout: int = 60) -> str:
    """Call a REST endpoint and extract a single field via a jq expression."""
    return _run(["api", endpoint, "--jq", expression], timeout=timeout).strip()


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


def current_user() -> str:
    """Return the login of the account ``gh`` is authenticated as."""
    login = api_jq("user", ".login")
    if not login:
        raise GhError("could not determine the authenticated GitHub user")
    return login


def list_repos(owner: str, limit: int = 1000) -> list[dict]:
    """Return every repository owned by ``owner`` (forks included)."""
    out = _run(
        ["repo", "list", owner, "--limit", str(limit), "--json",
         "name,isFork,parent,defaultBranchRef"]
    )
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise GhError("gh repo list returned invalid JSON") from exc


def default_branch(slug: str) -> str | None:
    """Return the default branch of ``owner/name`` or None when unreachable."""
    try:
        return api_jq(f"repos/{slug}", ".default_branch")
    except GhError:
        return None


def list_branches(slug: str) -> list[str]:
    """Return every branch name in ``slug``.

    The single-branch endpoint is unreliable: asking for a branch that does not
    exist can answer with the repository's default branch instead of a 404, so
    membership is decided from the full list.
    """
    try:
        data = api_json(f"repos/{slug}/branches?per_page=100")
    except GhError:
        return []
    return [item.get("name", "") for item in data if isinstance(item, dict)]


def compare_commits(fork: RepoRef, base_owner: str, base_branch: str,
                    head_branch: str) -> dict:
    """Compare an upstream branch against the same-named branch on a fork.

    ``status`` is one of ``behind``, ``ahead``, ``diverged`` or ``identical``.
    """
    endpoint = (
        f"repos/{fork.owner}/{fork.name}/compare/"
        f"{base_owner}:{base_branch}...{head_branch}"
    )
    return api_json(endpoint)


def commit_count(slug: str, branch: str) -> int:
    """Return how many commits ``branch`` has in ``slug``."""
    try:
        return int(api_jq(f"repos/{slug}/commits/{branch}", "length"))
    except (GhError, ValueError):
        return 0


def sync_repo(fork: RepoRef, source: RepoRef, branch: str) -> str:
    """Fast-forward ``fork`` from ``source`` on ``branch``.

    Raises :class:`GhError` when the sync cannot be completed.
    """
    return _run(
        ["repo", "sync", fork.slug, "--source", source.slug, "--branch", branch],
        timeout=180,
    )
