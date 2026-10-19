# SPDX-License-Identifier: MIT OR Apache-2.0

"""Human-readable rendering of an audit."""

from __future__ import annotations

from . import audit as audit_mod

TITLES = {
    audit_mod.BEHIND: "BEHIND (fast-forward, no conflict)",
    audit_mod.MISSING_BRANCH: "MISSING BRANCH (upstream branch absent from the fork)",
    audit_mod.DIVERGED: "DIVERGED (may conflict)",
    audit_mod.UNRELATED: "UNRELATED HISTORY (rewritten upstream, not comparable)",
    audit_mod.AHEAD: "AHEAD (fork is ahead of upstream)",
    audit_mod.IDENTICAL: "IDENTICAL (nothing to do)",
    audit_mod.ERROR: "ERRORS",
}

ORDER = [
    audit_mod.BEHIND,
    audit_mod.MISSING_BRANCH,
    audit_mod.DIVERGED,
    audit_mod.UNRELATED,
    audit_mod.AHEAD,
    audit_mod.IDENTICAL,
    audit_mod.ERROR,
]


def render(audit: audit_mod.Audit) -> str:
    """Return a plain-text report of the audit."""
    counts = audit.counts()
    lines: list[str] = []
    lines.append(f"owner: {audit.owner}   forks: {len(audit.forks)}")
    summary = "  ".join(
        f"{status}={counts.get(status, 0)}" for status in ORDER if counts.get(status)
    )
    if summary:
        lines.append(summary)
    lines.append("")

    for status in ORDER:
        states = audit.by_status(status)
        if not states:
            continue
        lines.append(f"=== {TITLES[status]}: {len(states)}")
        if status == audit_mod.IDENTICAL:
            for s in sorted(states, key=lambda x: x.name.lower()):
                lines.append(f"  {s.name:<38} <- {s.upstream}")
        elif status in (audit_mod.ERROR, audit_mod.UNRELATED):
            for s in sorted(states, key=lambda x: x.name.lower()):
                lines.append(f"  {s.name:<38} <- {s.upstream}: {s.error}")
        elif status == audit_mod.AHEAD:
            for s in sorted(states, key=lambda x: -x.ahead_by):
                lines.append(
                    f"  {s.name:<38} <- {s.upstream:<42} branch={s.branch:<8} +{s.ahead_by}"
                )
        elif status == audit_mod.DIVERGED:
            for s in sorted(states, key=lambda x: -x.behind_by):
                lines.append(
                    f"  {s.name:<38} <- {s.upstream:<42} branch={s.branch:<8} "
                    f"upstream+{s.behind_by} fork+{s.ahead_by}"
                )
        else:
            for s in sorted(states, key=lambda x: -x.behind_by):
                lines.append(
                    f"  {s.name:<38} <- {s.upstream:<42} branch={s.branch:<8} +{s.behind_by}"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
