# SPDX-License-Identifier: MIT OR Apache-2.0

"""Audit which of a user's forks lag behind their upstream."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from . import gh

# Buckets a fork can fall into, relative to its upstream.
BEHIND = "behind"
DIVERGED = "diverged"
AHEAD = "ahead"
IDENTICAL = "identical"
MISSING_BRANCH = "missing-branch"
UNRELATED = "unrelated"
ERROR = "error"

#: Buckets `forksync sync` touches without an explicit ``--status``.
DEFAULT_SYNCABLE = (BEHIND,)


@dataclass
class ForkState:
    """Audit result for a single fork."""

    name: str
    fork_owner: str
    fork_name: str
    upstream: str
    branch: str | None = None
    status: str = ERROR
    behind_by: int = 0
    ahead_by: int = 0
    fork_default_branch: str | None = None
    error: str | None = None

    @property
    def slug(self) -> str:
        return f"{self.fork_owner}/{self.fork_name}"

    @property
    def syncable(self) -> bool:
        """True when a fast-forward is possible and safe."""
        return self.status in DEFAULT_SYNCABLE

    def to_dict(self) -> dict:
        data = asdict(self)
        data["slug"] = self.slug
        data["syncable"] = self.syncable
        return data


@dataclass
class Audit:
    """Audit result for a whole account."""

    owner: str
    forks: list[ForkState] = field(default_factory=list)

    def by_status(self, status: str) -> list[ForkState]:
        return [f for f in self.forks if f.status == status]

    @property
    def syncable(self) -> list[ForkState]:
        return [f for f in self.forks if f.syncable]

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for fork in self.forks:
            counts[fork.status] = counts.get(fork.status, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "counts": self.counts(),
            "forks": [f.to_dict() for f in self.forks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Audit:
        audit = cls(owner=data["owner"])
        for item in data.get("forks", []):
            audit.forks.append(
                ForkState(
                    name=item["name"],
                    fork_owner=item["fork_owner"],
                    fork_name=item["fork_name"],
                    upstream=item["upstream"],
                    branch=item.get("branch"),
                    status=item.get("status", ERROR),
                    behind_by=item.get("behind_by", 0),
                    ahead_by=item.get("ahead_by", 0),
                    fork_default_branch=item.get("fork_default_branch"),
                    error=item.get("error"),
                )
            )
        return audit


def _audit_one(fork: dict, owner: str) -> ForkState:
    name = fork["name"]
    parent = fork.get("parent")
    if not parent:
        return ForkState(name, owner, name, "", status=ERROR, error="not a fork")

    upstream = f"{parent['owner']['login']}/{parent['name']}"
    state = ForkState(name, owner, name, upstream)

    upstream_branch = gh.default_branch(upstream)
    state.fork_default_branch = gh.default_branch(f"{owner}/{name}")
    if not upstream_branch:
        state.error = f"cannot read the default branch of {upstream}"
        return state
    state.branch = upstream_branch

    fork_branches = gh.list_branches(f"{owner}/{name}")
    if upstream_branch not in fork_branches:
        # The fork never carried the upstream's default branch. Syncing would
        # create it, which is conflict-free but rarely what the owner wants,
        # so it is reported separately and only synced on explicit request.
        state.status = MISSING_BRANCH
        state.behind_by = gh.commit_count(upstream, upstream_branch)
        return state

    try:
        data = gh.compare_commits(
            gh.RepoRef(owner, name),
            parent["owner"]["login"],
            upstream_branch,
            upstream_branch,
        )
    except gh.GhUnrelatedHistory as exc:
        state.status = UNRELATED
        state.error = str(exc)
        return state
    except gh.GhNotFound as exc:
        state.error = str(exc)
        return state
    except gh.GhError as exc:
        state.error = str(exc)
        return state

    state.status = data.get("status", ERROR)
    state.behind_by = data.get("behind_by", 0)
    state.ahead_by = data.get("ahead_by", 0)
    return state


def audit_forks(owner: str, workers: int = 8, limit: int = 1000) -> Audit:
    """Compare every fork owned by ``owner`` against its upstream."""
    repos = gh.list_repos(owner, limit=limit)
    forks = [r for r in repos if r.get("isFork") and r.get("parent")]
    audit = Audit(owner=owner)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        states = list(pool.map(lambda f: _audit_one(f, owner), forks))
    audit.forks = sorted(states, key=lambda s: s.name.lower())
    return audit


def save_audit(audit: Audit, path: str) -> None:
    """Write the audit to ``path`` as JSON."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(audit.to_dict(), handle, indent=2)


def load_audit(path: str) -> Audit:
    """Read a previously saved audit from ``path``."""
    with open(path, encoding="utf-8") as handle:
        return Audit.from_dict(json.load(handle))
