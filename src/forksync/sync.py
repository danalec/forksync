# SPDX-License-Identifier: MIT OR Apache-2.0

"""Fast-forward forks that lag behind their upstream."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import audit as audit_mod
from . import gh


@dataclass
class SyncOutcome:
    """Result of a single sync attempt."""

    slug: str
    upstream: str
    branch: str
    ok: bool
    message: str = ""


def sync_one(state: audit_mod.ForkState, owner: str) -> SyncOutcome:
    """Sync one fork. Never raises; failures are reported in the outcome."""
    if not state.branch:
        return SyncOutcome(state.slug, state.upstream, "?", False,
                           "no branch to sync")
    fork = gh.RepoRef(owner, state.fork_name)
    upstream_owner, upstream_name = state.upstream.split("/", 1)
    source = gh.RepoRef(upstream_owner, upstream_name)
    try:
        output = gh.sync_repo(fork, source, state.branch)
        return SyncOutcome(state.slug, state.upstream, state.branch, True,
                           output.strip())
    except gh.GhError as exc:
        return SyncOutcome(state.slug, state.upstream, state.branch, False,
                           str(exc))


def sync_all(states: list[audit_mod.ForkState], owner: str,
             workers: int = 4, dry_run: bool = False) -> list[SyncOutcome]:
    """Sync every given fork, optionally without touching the network."""
    if dry_run:
        return [
            SyncOutcome(s.slug, s.upstream, s.branch or "?", True, "dry-run")
            for s in states
        ]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda s: sync_one(s, owner), states))
