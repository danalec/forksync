# SPDX-License-Identifier: MIT OR Apache-2.0

"""Tests for the classification and reporting logic.

The API calls are out of scope here; what is worth pinning is the decision a
fork state turns into, because that decision is what decides whether a
repository gets rewritten.
"""

import unittest

from forksync import audit, report


def state(**kwargs) -> audit.ForkState:
    base = dict(
        name="example",
        fork_owner="danalec",
        fork_name="example",
        upstream="someone/example",
        branch="main",
    )
    base.update(kwargs)
    return audit.ForkState(**base)


class ClassificationTests(unittest.TestCase):
    def test_behind_is_syncable(self):
        self.assertTrue(state(status=audit.BEHIND).syncable)

    def test_diverged_is_not_syncable(self):
        self.assertFalse(state(status=audit.DIVERGED).syncable)

    def test_ahead_is_not_syncable(self):
        self.assertFalse(state(status=audit.AHEAD).syncable)

    def test_missing_branch_is_not_syncable_by_default(self):
        """Creating a branch is conflict-free but rarely what the owner wants."""
        self.assertFalse(state(status=audit.MISSING_BRANCH).syncable)

    def test_unrelated_is_not_syncable(self):
        self.assertFalse(state(status=audit.UNRELATED).syncable)

    def test_default_syncable_set(self):
        self.assertEqual(audit.DEFAULT_SYNCABLE, (audit.BEHIND,))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.audit = audit.Audit(owner="danalec", forks=[
            state(name="b", status=audit.BEHIND, behind_by=5),
            state(name="a", status=audit.DIVERGED),
            state(name="c", status=audit.IDENTICAL),
        ])

    def test_counts(self):
        self.assertEqual(self.audit.counts(), {audit.BEHIND: 1, audit.DIVERGED: 1,
                                               audit.IDENTICAL: 1})

    def test_by_status(self):
        self.assertEqual([f.name for f in self.audit.by_status(audit.BEHIND)], ["b"])

    def test_roundtrip(self):
        restored = audit.Audit.from_dict(self.audit.to_dict())
        self.assertEqual(restored.owner, "danalec")
        self.assertEqual([f.name for f in restored.forks], ["b", "a", "c"])
        self.assertEqual(restored.by_status(audit.BEHIND)[0].behind_by, 5)


class ReportTests(unittest.TestCase):
    def test_every_status_gets_a_section(self):
        text = report.render(audit.Audit(owner="danalec", forks=[
            state(name="b", status=audit.BEHIND, behind_by=5),
            state(name="u", status=audit.UNRELATED, error="no common ancestor"),
        ]))
        self.assertIn("BEHIND (fast-forward, no conflict): 1", text)
        self.assertIn("UNRELATED HISTORY", text)
        self.assertIn("no common ancestor", text)

    def test_forks_with_the_same_name_are_told_apart(self):
        text = report.render(audit.Audit(owner="danalec", forks=[
            state(name="same", status=audit.BEHIND),
            state(name="same", status=audit.AHEAD),
        ]))
        self.assertIn("BEHIND (fast-forward, no conflict): 1", text)
        self.assertIn("AHEAD (fork is ahead of upstream): 1", text)


if __name__ == "__main__":
    unittest.main()
