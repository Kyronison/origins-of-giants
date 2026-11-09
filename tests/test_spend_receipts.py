"""Offline request accounting: never load or write the real pipeline database."""
import asyncio
import os
import socket
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_bootstrap = tempfile.TemporaryDirectory(prefix="spend-tests-")
os.environ.setdefault("DATA_DIR", _bootstrap.name)
from orchestrator import config, spend, money, llm


class SpendReceipts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="spend-case-")
        self.addCleanup(self.tmp.cleanup)
        self.paths = patch.object(config, "DATA", Path(self.tmp.name))
        self.paths.start(); self.addCleanup(self.paths.stop)
        net = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        net.start(); self.addCleanup(net.stop)
        self.sdk = SimpleNamespace()
        mods = patch.dict("sys.modules", {"fal_client": self.sdk})
        mods.start(); self.addCleanup(mods.stop)
        spend.ensure_baseline("en", 10, 8, 2)
        spend.ensure_baseline("es", 20, 15, 5)

    def rows(self):
        with closing(sqlite3.connect(config.DATA / "spend.sqlite3")) as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute("SELECT * FROM requests")]

    @staticmethod
    def image_args():
        return {"image_size": {"width": 1536, "height": 864}, "sync_mode": True}

    def test_sync_callback_and_duplicate_job_are_idempotent(self):
        seen = []
        def original(application, arguments, *, on_enqueue=None):
            on_enqueue("fal-job-1")
            return {"images": [{"url": "data:image/png;base64,private"}], "cost": 999}
        self.sdk.subscribe = original
        with spend.scope("en", "assets"):
            for _ in range(2):
                self.sdk.subscribe("fal-ai/flux/schnell", self.image_args(), on_enqueue=seen.append)
        self.assertIs(self.sdk.subscribe, original)
        self.assertEqual(seen, ["fal-job-1"] * 2)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["request_id"], "fal-job-1")
        self.assertIsNone(self.rows()[0]["confirmed_usd"])
        self.assertAlmostEqual(spend.summary("en")["accounted_usd"], 10.006)
        self.assertNotIn("private", str(self.rows()))

    def test_parallel_workers_inherit_video_and_other_video_is_separate(self):
        def original(application, arguments, *, on_enqueue=None):
            on_enqueue("job-" + str(arguments["n"]))
            return {}
        self.sdk.subscribe = original
        with spend.scope("en", "assets"):
            with ThreadPoolExecutor(16) as pool:
                list(pool.map(lambda n: self.sdk.subscribe("unknown-model", {"n": n}), range(32)))
        with spend.scope("es", "assets"):
            self.sdk.subscribe("unknown-model", {"n": "es"})
        self.assertEqual(spend.summary("en")["requests"], 32)
        self.assertEqual(spend.summary("es")["requests"], 1)
        self.assertEqual(spend.summary("en")["unknown_requests"], 32)

    def test_scope_restores_hooks_on_error_and_rejects_concurrent_video(self):
        original = lambda *a, **kw: {}
        self.sdk.subscribe = original
        with self.assertRaisesRegex(RuntimeError, "intentional"):
            with spend.scope("en", "assets"):
                with self.assertRaisesRegex(RuntimeError, "Two video"):
                    with spend.scope("es", "assets"):
                        pass
                raise RuntimeError("intentional")
        self.assertIs(self.sdk.subscribe, original)
        self.assertIsNone(spend.current())

    def test_failure_keeps_provider_job_and_retry_is_distinct(self):
        counter = [0]
        def original(application, arguments, *, on_enqueue=None):
            counter[0] += 1
            on_enqueue("attempt-" + str(counter[0]))
            if counter[0] == 1:
                raise TimeoutError("must not persist raw request or secrets")
            return {}
        self.sdk.subscribe = original
        with spend.scope("en", "assets"):
            with self.assertRaises(TimeoutError):
                self.sdk.subscribe("unknown", {})
            self.sdk.subscribe("unknown", {})
        result = spend.summary("en")
        self.assertEqual(result["requests"], 2)
        self.assertEqual(result["unknown_requests"], 2)
        self.assertEqual(result["unresolved_requests"], 1)
        self.assertNotIn("secrets", str(self.rows()))

    def test_failure_before_queue_is_unknown_not_zero(self):
        def original(*args, **kwargs):
            raise ConnectionError("lost before receipt")
        self.sdk.subscribe = original
        with spend.scope("es", "assets"), self.assertRaises(ConnectionError):
            self.sdk.subscribe("unknown", {})
        row = self.rows()[0]
        self.assertIsNone(row["request_id"])
        self.assertIsNone(row["confirmed_usd"])
        self.assertFalse(spend.summary("es")["complete"])

    def test_nested_subscribe_submit_is_one_receipt(self):
        self.sdk.submit = lambda *a, **kw: SimpleNamespace(request_id="nested-job", get=lambda: {})
        def original(application, arguments, *, on_enqueue=None):
            handle = self.sdk.submit(application, arguments)
            on_enqueue(handle.request_id)
            return handle.get()
        self.sdk.subscribe = original
        with spend.scope("en", "assets"):
            self.sdk.subscribe("unknown", {})
        self.assertEqual(len(self.rows()), 1)

    def test_async_callback_and_submit_handle(self):
        seen = []
        async def callback(job):
            seen.append(job)
        async def subscribe(application, arguments, *, on_enqueue=None):
            result = on_enqueue("async-subscribe")
            if asyncio.iscoroutine(result):
                await result
            return {}
        async def get():
            return {"images": []}
        async def submit(*a, **kw):
            return SimpleNamespace(request_id="async-submit", get=get)
        self.sdk.subscribe_async, self.sdk.submit_async = subscribe, submit
        async def exercise():
            with spend.scope("es", "assets"):
                await self.sdk.subscribe_async("unknown", {}, on_enqueue=callback)
                handle = await self.sdk.submit_async("unknown", {})
                await handle.get()
                await handle.get()
        # All fake awaitables finish immediately; drive them without a Windows
        # event loop, whose self-pipe otherwise opens a local test socket.
        coroutine = exercise()
        with self.assertRaises(StopIteration):
            coroutine.send(None)
        self.assertEqual(seen, ["async-subscribe"])
        self.assertEqual(len(self.rows()), 2)
        self.assertTrue(all(r["state"] == "succeeded" for r in self.rows()))

    def test_run_without_provider_id_retains_local_attempt_and_unknown_price(self):
        self.sdk.run = lambda *a, **kw: {"cost": 5}
        with spend.scope("en", "assets"):
            self.sdk.run("unpriced-model", {})
        row = self.rows()[0]
        self.assertIsNone(row["request_id"])
        self.assertIsNone(row["confirmed_usd"])
        self.assertEqual(spend.summary("en")["unknown_requests"], 1)

    def test_explicit_confirmation_replaces_estimate_without_adding_twice(self):
        def original(application, arguments, *, on_enqueue=None):
            on_enqueue("priced")
            return {}
        self.sdk.subscribe = original
        with spend.scope("en", "assets"):
            self.sdk.subscribe("fal-ai/flux/schnell", self.image_args())
        for _ in range(2):
            spend.record_confirmed("fal", "priced", 0.01, "test-billing-receipt")
        result = spend.summary("en")
        self.assertAlmostEqual(result["accounted_usd"], 10.01)
        self.assertEqual(result["estimated_usd"], 0)
        with self.assertRaises(ValueError):
            spend.record_confirmed("fal", "priced", 0.02, "conflicting-receipt")

    def test_provider_id_cannot_move_between_videos(self):
        def original(application, arguments, *, on_enqueue=None):
            on_enqueue("same-job")
            return {}
        self.sdk.subscribe = original
        with spend.scope("en", "assets"):
            self.sdk.subscribe("unknown", {})
        with spend.scope("es", "assets"), self.assertRaises(ValueError):
            self.sdk.subscribe("unknown", {})
        self.assertEqual(spend.summary("en")["requests"], 1)

    def test_openrouter_exact_price_zero_unknown_and_error(self):
        response = SimpleNamespace(id="or-1", usage=SimpleNamespace(cost=0.123456, model_extra={}))
        with spend.scope("en", "script"):
            for _ in range(2):
                spend.openrouter_call(lambda: response, model="test")
            spend.openrouter_call(lambda: SimpleNamespace(id="or-2", usage=SimpleNamespace(cost=0, model_extra={})), model="test")
            spend.openrouter_call(lambda: SimpleNamespace(id="or-3", usage=None), model="test")
            with self.assertRaises(TimeoutError):
                spend.openrouter_call(lambda: (_ for _ in ()).throw(TimeoutError()), model="test")
        result = spend.summary("en")
        self.assertEqual(result["requests"], 4)
        self.assertAlmostEqual(result["confirmed_usd"], 0.123456)
        self.assertEqual(result["unknown_requests"], 2)
        self.assertEqual(result["unresolved_requests"], 1)

    def test_legacy_baseline_is_immutable_and_stage_estimates_are_not_added_twice(self):
        payload = {"cost_usd": 14, "fal_usd": 3}
        with patch.object(money.db, "get", return_value={"payload": payload}), patch.object(money, "_llm_cost_by_video", return_value={"new": 8}):
            money.begin_stage("new")
            payload["cost_usd"] = 999
            money.begin_stage("new")
            self.assertEqual(money.spent("new"), 14)
            with patch.object(money.db, "update") as update:
                money.reconcile("new")
                self.assertEqual(update.call_args.kwargs["payload"]["cost_usd"], 14)
        self.assertEqual(spend.baseline("new")["amount_usd"], 14)

    def test_unknown_and_estimated_charges_are_explicit_in_report_note(self):
        with spend.scope("en", "assets"):
            spend._begin("fal", "unknown")
            spend._begin("fal", "fal-ai/flux/schnell", self.image_args())
        note = money._accounting_note(spend.summary("en"))
        self.assertIn("неизвестная цена", note)
        self.assertIn("итог неполный", note)
        self.assertIn("оценка", note)

    def test_gpt_high_price_is_unknown_not_medium_fallback(self):
        price, source = spend._estimate_fal("openai/gpt-image-2.5/flare/text-to-image", {"quality": "high"})
        self.assertIsNone(price)
        self.assertIsNone(source)

    def test_llm_paid_create_uses_the_receipt_path(self):
        response = SimpleNamespace(id="actual-sdk-response", usage=SimpleNamespace(cost=0.02, model_extra={}))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
        with patch.object(llm, "client", return_value=client), spend.scope("en", "script"):
            self.assertIs(llm._paid_create(model="test", messages=[]), response)
        self.assertEqual(self.rows()[0]["request_id"], "actual-sdk-response")

    def test_post_purchase_receipt_write_failure_does_not_retry_or_discard_result(self):
        calls = []
        def original(application, arguments, *, on_enqueue=None):
            calls.append(application)
            on_enqueue("durable-job")
            return {"images": []}
        self.sdk.subscribe = original
        update = spend._update
        def fail_final(attempt, **fields):
            if fields.get("state") == "succeeded":
                raise sqlite3.OperationalError("disk temporarily unavailable")
            return update(attempt, **fields)
        with spend.scope("en", "assets"), patch.object(spend, "_update", side_effect=fail_final):
            result = self.sdk.subscribe("unknown", {})
        self.assertEqual(result, {"images": []})
        self.assertEqual(calls, ["unknown"])
        self.assertEqual(self.rows()[0]["request_id"], "durable-job")
        self.assertEqual(spend.summary("en")["unresolved_requests"], 1)


if __name__ == "__main__":
    unittest.main()
