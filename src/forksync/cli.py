# SPDX-License-Identifier: MIT OR Apache-2.0

"""Command line interface for forksync."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

from . import audit as audit_mod
from . import gh, report, sync

DEFAULT_REPORT = os.path.join(tempfile.gettempdir(), "forksync-audit.json")


def _owner(args) -> str:
    if args.owner:
        return args.owner
    return gh.current_user()


def cmd_check(args) -> int:
    gh.require_gh()
    owner = _owner(args)
    print(f"Auditing forks of {owner} ...", file=sys.stderr)
    result = audit_mod.audit_forks(owner, workers=args.workers)
    audit_mod.save_audit(result, args.out)
    counts = result.counts()
    print(
        "  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        file=sys.stderr,
    )
    print(f"  report written to {args.out}", file=sys.stderr)
    if not args.quiet:
        sys.stdout.write(report.render(result))
    return 0


def cmd_report(args) -> int:
    result = audit_mod.load_audit(args.out)
    sys.stdout.write(report.render(result))
    return 0


def cmd_sync(args) -> int:
    gh.require_gh()
    owner = _owner(args)
    result = audit_mod.load_audit(args.out)
    wanted = (
        {s.strip() for s in args.status.split(",")}
        if args.status
        else set(audit_mod.DEFAULT_SYNCABLE)
    )
    states = [s for s in result.forks if s.status in wanted]
    if not states:
        print("Nothing to sync.", file=sys.stderr)
        return 0
    if args.dry_run:
        for s in states:
            print(f"DRY-RUN {s.slug} <- {s.upstream} ({s.branch})")
        print(f"\n{len(states)} fork(s) would be synced.", file=sys.stderr)
        return 0

    print(f"Syncing {len(states)} fork(s) ...", file=sys.stderr)
    outcomes = sync.sync_all(states, owner, workers=args.workers)
    failed = [o for o in outcomes if not o.ok]
    for outcome in outcomes:
        marker = "OK  " if outcome.ok else "FAIL"
        print(f"[{marker}] {outcome.slug} <- {outcome.upstream} ({outcome.branch})")
        if not outcome.ok:
            print(f"        {outcome.message}", file=sys.stderr)
    print(f"\n{len(outcomes) - len(failed)} ok, {len(failed)} failed", file=sys.stderr)
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forksync",
        description="Audit and fast-forward your GitHub forks.",
    )
    parser.add_argument(
        "--owner",
        help="GitHub account to audit (defaults to the authenticated user).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Compare every fork against its upstream.")
    check.add_argument("--out", default=DEFAULT_REPORT, help="Where to write the JSON report.")
    check.add_argument("--workers", type=int, default=8, help="Parallel API calls.")
    check.add_argument("--quiet", action="store_true", help="Do not print the text report.")
    check.set_defaults(func=cmd_check)

    rep = sub.add_parser("report", help="Re-print a saved report.")
    rep.add_argument("--out", default=DEFAULT_REPORT, help="Path of the JSON report.")
    rep.set_defaults(func=cmd_report)

    syn = sub.add_parser("sync", help="Fast-forward forks that are behind.")
    syn.add_argument("--out", default=DEFAULT_REPORT, help="Path of the JSON report.")
    syn.add_argument(
        "--status",
        help=(
            "Comma-separated statuses to sync. Defaults to 'behind'. "
            "Use 'missing-branch' to also create upstream branches absent "
            "from the fork."
        ),
    )
    syn.add_argument("--dry-run", action="store_true", help="Show what would be synced.")
    syn.add_argument("--workers", type=int, default=4, help="Parallel syncs.")
    syn.set_defaults(func=cmd_sync)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except gh.GhError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
