import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from dispatcher.idempotency import (
    SQLiteLeaseStore,
    artifact_idempotency_key,
    task_key,
)


class IdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "dispatcher.sqlite3"
        self.store = SQLiteLeaseStore(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_task_key_is_stable_and_normalized(self):
        self.assertEqual(task_key("Owner/Repo", 42), "owner/repo#42")

    def test_task_key_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            task_key("owner", 1)
        with self.assertRaises(ValueError):
            task_key("owner/repo", True)

    def test_first_claim_is_acquired_and_duplicate_is_rejected(self):
        first = self.store.claim(key="owner/repo#1", owner="run-1")
        second = self.store.claim(key="owner/repo#1", owner="run-2")
        self.assertTrue(first.acquired)
        self.assertEqual(first.status, "acquired")
        self.assertFalse(second.acquired)
        self.assertEqual(second.status, "already_running")

    def test_completed_task_cannot_be_claimed_again(self):
        claim = self.store.claim(key="owner/repo#2", owner="run-1")
        self.assertTrue(self.store.finish(key="owner/repo#2", owner="run-1", fencing_token=claim.fencing_token, success=True))
        result = self.store.claim(key="owner/repo#2", owner="run-2")
        self.assertFalse(result.acquired)
        self.assertEqual(result.status, "already_completed")

    def test_wrong_owner_cannot_finish_or_renew(self):
        claim = self.store.claim(key="owner/repo#3", owner="run-1")
        self.assertFalse(self.store.finish(key="owner/repo#3", owner="run-2", fencing_token=claim.fencing_token, success=True))
        self.assertFalse(self.store.renew(key="owner/repo#3", owner="run-2", fencing_token=claim.fencing_token))

    def test_failed_task_can_be_reclaimed(self):
        claim = self.store.claim(key="owner/repo#4", owner="run-1")
        self.assertTrue(self.store.finish(key="owner/repo#4", owner="run-1", fencing_token=claim.fencing_token, success=False, error="tests failed"))
        next_claim = self.store.claim(key="owner/repo#4", owner="run-2")
        self.assertTrue(next_claim.acquired)
        self.assertEqual(next_claim.status, "reclaimed")

    def test_lease_renewal_succeeds_only_for_current_live_owner(self):
        claim = self.store.claim(key="owner/repo#5", owner="run-1")
        self.assertTrue(self.store.renew(key="owner/repo#5", owner="run-1", fencing_token=claim.fencing_token))
        self.assertFalse(self.store.renew(key="owner/repo#5", owner="run-2", fencing_token=claim.fencing_token))

    def test_run_id_is_idempotent(self):
        self.store.claim(key="owner/repo#6", owner="run-1")
        self.assertTrue(self.store.record_run(run_id="gha-100", key="owner/repo#6", owner="run-1", status="started"))
        self.assertFalse(self.store.record_run(run_id="gha-100", key="owner/repo#6", owner="run-1", status="started"))

    def test_concurrent_claims_are_single_flight_on_shared_sqlite(self):
        barrier = threading.Barrier(6)
        results = []
        lock = threading.Lock()
        def worker(index):
            store = SQLiteLeaseStore(self.db)
            barrier.wait()
            result = store.claim(key="owner/repo#7", owner=f"run-{index}")
            with lock:
                results.append(result)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(result.acquired for result in results), 1)

    def test_artifact_key_is_stable_and_opaque(self):
        first = artifact_idempotency_key("Owner/Repo", 10, "task")
        second = artifact_idempotency_key("owner/repo", 10, "task")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotIn("task", first)

    def test_expired_owner_cannot_finish_after_lease_expiry(self):
        old_claim = self.store.claim(key="owner/repo#9", owner="run-old")
        with sqlite3.connect(self.db) as db:
            db.execute(
                "UPDATE dispatcher_leases SET lease_expires_at = ? WHERE task_key = ?",
                ("2000-01-01T00:00:00Z", "owner/repo#9"),
            )
        reclaimed = self.store.claim(key="owner/repo#9", owner="run-new")
        self.assertTrue(reclaimed.acquired)
        self.assertFalse(self.store.finish(key="owner/repo#9", owner="run-old", fencing_token=old_claim.fencing_token, success=True))
        self.assertTrue(self.store.finish(key="owner/repo#9", owner="run-new", fencing_token=reclaimed.fencing_token, success=True))

    def test_same_owner_stale_attempt_is_fenced_after_reclaim(self):
        old = self.store.claim(key="owner/repo#10", owner="stable-worker")
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE dispatcher_leases SET lease_expires_at = ? WHERE task_key = ?", ("2000-01-01T00:00:00Z", "owner/repo#10"))
        new = self.store.claim(key="owner/repo#10", owner="stable-worker")
        self.assertNotEqual(old.fencing_token, new.fencing_token)
        self.assertFalse(self.store.finish(key="owner/repo#10", owner="stable-worker", fencing_token=old.fencing_token, success=True))
        self.assertFalse(self.store.renew(key="owner/repo#10", owner="stable-worker", fencing_token=old.fencing_token))
        self.assertTrue(self.store.finish(key="owner/repo#10", owner="stable-worker", fencing_token=new.fencing_token, success=True))

    def test_lease_duration_must_be_bounded(self):
        with self.assertRaises(ValueError):
            self.store.claim(key="owner/repo#8", owner="run", lease_seconds=1)


if __name__ == "__main__":
    unittest.main()
