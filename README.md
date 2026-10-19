# forksync

Find which of your GitHub forks fell behind their upstream, and fast-forward
them without a single merge conflict.

A fork that is *behind* has no commits of its own on that branch, so pulling
upstream is a pure fast-forward — it cannot conflict. A fork that is *diverged*
is ahead **and** behind, and might. `forksync` sorts your forks into those
buckets so you only ever touch the safe ones.

Built on the [GitHub CLI](https://cli.github.com/) (`gh`), so it reuses the
authentication you already have.

## Install

```sh
pip install .
```

or run it from a clone without installing:

```sh
python -m forksync check
```

Needs Python 3.9+ and `gh` on `PATH`, already authenticated:

```sh
gh auth login
```

## Try it

Audit every fork you own and print what is behind:

```sh
forksync check
```

```
owner: danalec   forks: 87
behind=14  diverged=10  ahead=6  identical=54  error=3

=== BEHIND (fast-forward, no conflict): 14
  ladybird                               <- LadybirdBrowser/ladybird                   branch=master   +46
  kuna                                   <- Noelo-Lab/kuna                             branch=main     +21
  cagent                                 <- docker/docker-agent                        branch=main     +19
  ...
```

See what a sync would do, then do it:

```sh
forksync sync --dry-run
forksync sync
```

`sync` only ever touches forks whose status is `behind`. Diverged, ahead and
identical forks are never modified.

Audit somebody else's account, and re-print a report you saved earlier:

```sh
forksync --owner someone check
forksync report --out /tmp/forksync-audit.json
```

## Develop

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

The tests are pure — no network, no `gh`, no account. They pin the
classification, because that is the decision that decides whether a
repository gets rewritten.

## Buckets

| Status | Meaning | Synced? |
|---|---|---|
| `behind` | Upstream has commits the fork lacks, and the fork has none of its own | yes |
| `missing-branch` | The fork does not carry the upstream's default branch at all | only with `--status missing-branch` |
| `diverged` | Fork is both ahead and behind | no, may conflict |
| `unrelated` | The two branches share no common ancestor — upstream history was rewritten | no, not comparable |
| `ahead` | Fork has commits upstream lacks | no, nothing to pull |
| `identical` | Fork matches upstream | no, nothing to do |
| `error` | The API call failed | investigate |

`missing-branch` is kept out of the default sync on purpose: the branch would
be *created* on your fork, which is conflict-free but rarely what you wanted
when the fork carries its own work on a different branch. Ask for it
explicitly.

## How the comparison works

For every fork, `forksync` reads the upstream's default branch and compares it
against the **same-named** branch on the fork:

```
GET /repos/{fork_owner}/{fork_name}/compare/{upstream_owner}:{branch}...{branch}
```

Two details that are easy to get wrong, and that this tool gets right:

- The comparison crosses repositories. Comparing a fork against itself always
  returns `identical` — a silent false negative that looks like "nothing to
  do".
- The same branch name is used for the sync, because `gh repo sync --branch X`
  writes upstream's `X` into the fork's `X`.

A fork is only reported as `behind` when the compare says so. Nothing is
inferred from commit counts.

## Docs

| File | What it is |
|---|---|
| [`src/forksync/gh.py`](src/forksync/gh.py) | The `gh` wrapper — every API call goes through it |
| [`src/forksync/audit.py`](src/forksync/audit.py) | The audit: which forks are behind which upstream |
| [`src/forksync/sync.py`](src/forksync/sync.py) | The sync, one fork at a time |
| [`src/forksync/report.py`](src/forksync/report.py) | The text report |
| [`src/forksync/cli.py`](src/forksync/cli.py) | `check`, `report`, `sync` |
| [`tests/test_forksync.py`](tests/test_forksync.py) | The classification tests — the decision that decides whether a repository gets rewritten |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | Tests and lint on Linux, Windows and macOS |
| [`COPYING`](COPYING) | The MIT / Apache-2.0 split and the commercial-use terms |

## License

Dual-licensed **MIT OR Apache-2.0** — the full map is in [`COPYING`](COPYING):

- **MIT OR Apache-2.0**: everything. There is no Apache-2.0-only subsystem, so
  every file carries the same `SPDX-License-Identifier: MIT OR Apache-2.0`
  header.
- Commercial use is intended under Apache-2.0, which is the license this
  project intends for commercial deployment; the MIT option remains available
  to anyone who prefers its terms. For commercial licensing terms and rates,
  contact the author.

Full texts: `LICENSE-MIT`, `LICENSE-APACHE`. Third-party notices: `NOTICE`.
