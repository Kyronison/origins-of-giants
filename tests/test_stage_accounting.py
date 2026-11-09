"""Queue and manual helpers must use the same per-request accounting boundary."""
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import config, db, main, money, spend


class StageAccountingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        data = Path(folder.name)
        for guard in (
            patch.multiple(config, DATA=data, VIDEOS=data / "videos"),
            patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")),
            patch.object(money, "fal_left", side_effect=AssertionError("Shared balance cannot price a stage")),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        self.vid = db.add("accounting-test", "Accounting test", {"cost_usd": 4.0, "fal_usd": 1.5})

    def receipt(self, request_id):
        return spend.openrouter_call(
            lambda: SimpleNamespace(id=request_id, usage=SimpleNamespace(cost=0.25)),
            model="test-model")

    def test_failed_stage_reconciles_its_receipt_without_shared_balance(self):
        failure = RuntimeError("stage failed after its paid request")

        def stage(vid):
            self.assertEqual(spend.current().video_id, vid)
            self.receipt("paid-stage")
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            main._execute(stage, self.vid, "script")
        self.assertIs(caught.exception, failure)
        self.assertEqual(db.get(self.vid)["payload"]["cost_usd"], 4.25)
        self.assertIsNone(spend.current())

    def test_manual_paid_helper_adds_to_existing_baseline_once(self):
        main._execute(lambda _: self.receipt("paid-stage"), self.vid, "script")

        def helper():
            self.assertEqual(spend.current().stage, "motion_shorts")
            self.receipt("paid-manual")
            # Legacy helper totals must not be added to receipts a second time.
            db.update(self.vid, payload={"cost_usd": 999.0})
            return "done"

        self.assertEqual(main.video_command(helper, self.vid, "motion_shorts"), "done")
        self.assertEqual(db.get(self.vid)["payload"]["cost_usd"], 4.5)
        self.assertEqual(spend.summary(self.vid)["requests"], 2)
        self.assertIsNone(spend.current())


if __name__ == "__main__":
    unittest.main()
