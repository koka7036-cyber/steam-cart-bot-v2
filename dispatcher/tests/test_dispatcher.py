import unittest

from dispatcher.dispatcher import select_next_task, validate_issue


def issue(number=1, title="Add focused parser regression tests", body=None, labels=None, state="open"):
    return {
        "number": number,
        "title": title,
        "body": body if body is not None else (
            "Implement a bounded regression test for the pure order parser helper. "
            "Only change tests/test_order_parser.py."
        ),
        "labels": labels if labels is not None else [{"name": "codex-ready"}],
        "state": state,
    }


class DispatcherPolicyTests(unittest.TestCase):
    def test_accepts_only_explicitly_labeled_actionable_issue(self):
        self.assertTrue(validate_issue(issue()).eligible)

    def test_rejects_missing_opt_in_label(self):
        decision = validate_issue(issue(labels=[]))
        self.assertFalse(decision.eligible)
        self.assertIn("codex-ready", decision.reason)

    def test_rejects_closed_issue(self):
        self.assertFalse(validate_issue(issue(state="closed")).eligible)

    def test_blocking_label_wins(self):
        self.assertFalse(validate_issue(issue(labels=[{"name": "codex-ready"}, {"name": "blocked"}])).eligible)

    def test_rejects_protected_paths(self):
        for path in ("start.bat", ".github/workflows/unsafe.yml", "../secrets/token.txt", "data/orders.json"):
            body = f"Fix parser behavior in {path} with tests and documentation. " * 2
            self.assertFalse(validate_issue(issue(body=body)).eligible, path)

    def test_rejects_live_operations(self):
        body = (
            "Implement a change to perform live sale through Steam POST and test it. "
            "This scope intentionally includes real transactions and mutations."
        )
        self.assertFalse(validate_issue(issue(body=body)).eligible)

    def test_does_not_reject_explicit_safety_prohibitions(self):
        body = (
            "Implement a parser-only regression test. Do not touch inventory, runtime data, "
            "credentials, auto-start, or perform live Steam, FunPay, or Playerok operations. "
            "Only modify tests/test_order_parser.py."
        )
        self.assertTrue(validate_issue(issue(body=body)).eligible)

    def test_rejects_oversized_issue_body(self):
        self.assertFalse(validate_issue(issue(body="x" * 6001)).eligible)

    def test_rejects_non_actionable_short_issue(self):
        self.assertFalse(validate_issue(issue(title="Improve things", body="Please improve things.")).eligible)

    def test_selects_exactly_one_highest_priority_then_lowest_number(self):
        a = issue(number=10, labels=[{"name": "codex-ready"}, {"name": "priority:low"}])
        b = issue(number=12, labels=[{"name": "codex-ready"}, {"name": "priority:high"}])
        c = issue(number=11, labels=[{"name": "codex-ready"}, {"name": "priority:high"}])
        selected = select_next_task([a, b, c])
        self.assertEqual(selected.issue_number, 11)

    def test_no_eligible_issues_returns_none(self):
        self.assertIsNone(select_next_task([issue(labels=[]), issue(number=2, state="closed")]))

    def test_invalid_labels_fail_closed(self):
        self.assertFalse(validate_issue(issue(labels="codex-ready")).eligible)

    def test_invalid_issue_number_fails_closed(self):
        for number in (True, 0, -1, 2_147_483_648, "5"):
            self.assertFalse(validate_issue(issue(number=number)).eligible)


if __name__ == "__main__":
    unittest.main()
