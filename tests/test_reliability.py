"""Offline regression suite. All data is temporary; network access is forbidden."""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, Mock

_data = tempfile.TemporaryDirectory(prefix="origins-tests-")
os.environ["DATA_DIR"] = _data.name
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from orchestrator import config, db, gates, locking, telegram, llm, money, main
from orchestrator.stages import qc, thumbcheck, assets, metrics, stillcheck, preflight


class Reliability(unittest.TestCase):
    def setUp(self):
        from orchestrator import config as _cfg
        self._strict = _cfg.STRICT_GATES; _cfg.STRICT_GATES = True   # 07.10: строгий режим проверяется явно
        self.addCleanup(setattr, _cfg, 'STRICT_GATES', self._strict)
        self.net = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in tests"))
        self.net.start()
        self.folder = tempfile.TemporaryDirectory(dir=_data.name)
        self.data = Path(self.folder.name)
        self.paths = patch.multiple(config, DATA=self.data, VIDEOS=self.data / "videos", RENDER_TMP=self.data / "render")
        self.paths.start()
        self.chat = patch.multiple(telegram, CHAT="111", CACHE=self.data / "tg_chat", TOKEN="test")
        self.chat.start()
        self.env = patch.dict(os.environ, {"TELEGRAM_ALLOWED_USER_IDS": ""})
        self.env.start()
        self.vid = db.add("example", "Example", {"script": {"script": "Reviewed text"}})
        self.d = db.video_dir(self.vid)
        (self.d / "script.md").write_text("Reviewed text", encoding="utf-8")

    def tearDown(self):
        self.env.stop(); self.chat.stop(); self.paths.stop(); self.net.stop()
        self.folder.cleanup()

    def update(self, user=111, chat=111, data=None, text=None):
        message = {"chat": {"id": chat}, "from": {"id": user}, "text": text}
        if data is not None:
            return {"update_id": 1, "callback_query": {"id": "cb", "from": {"id": user}, "message": message, "data": data}}
        return {"update_id": 1, "message": message}

    def test_telegram_checks_both_chat_and_sender(self):
        for u in (self.update(chat=999), self.update(user=999), self.update(user=999, data="approve:x")):
            self.assertFalse(telegram._authorized(u))
        self.assertTrue(telegram._authorized(self.update(data="approve:x")))

    def test_telegram_group_requires_allowlist(self):
        with patch.object(telegram, "CHAT", "-111"):
            self.assertFalse(telegram._authorized(self.update(chat=-111)))
            with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USER_IDS": "111,222"}):
                self.assertTrue(telegram._authorized(self.update(chat=-111)))
                self.assertFalse(telegram._authorized(self.update(user=999, chat=-111)))

    def test_first_sender_cannot_pair_bot(self):
        with patch.object(telegram, "CHAT", None):
            self.assertFalse(telegram._authorized(self.update()))
            self.assertFalse(telegram.CACHE.exists())

    def test_unauthorized_callback_cannot_mutate_queue(self):
        response = {"ok": True, "result": [self.update(user=999, data="approve:" + self.vid)]}
        with patch.object(telegram.requests, "get", return_value=Mock(json=lambda: response)), patch.object(telegram.requests, "post") as post:
            telegram.poll()
        self.assertEqual(db.get(self.vid)["status"], "idea")
        post.assert_not_called()

    def test_unknown_callback_cannot_reject(self):
        with self.assertRaises(ValueError): telegram._action("anything", self.vid)
        self.assertEqual(db.get(self.vid)["status"], "idea")

    def test_text_reject_and_fix(self):
        db.update(self.vid, "approved_script")
        telegram._action("reject", self.vid)
        self.assertEqual(db.get(self.vid)["status"], "rejected")
        (self.d / "script_draft.json").write_text("old")
        telegram._action("fix", self.vid, "New opening")
        self.assertFalse((self.d / "script_draft.json").exists())
        self.assertEqual(db.get(self.vid)["payload"]["fix_note"], "New opening")

    def test_payload_updates_are_atomic(self):
        barrier = threading.Barrier(12)
        def worker(i):
            barrier.wait()
            db.update(self.vid, payload={f"worker{i}": i})
        with concurrent.futures.ThreadPoolExecutor(12) as pool:
            list(pool.map(worker, range(12)))
        p = db.get(self.vid)["payload"]
        self.assertTrue(all(p[f"worker{i}"] == i for i in range(12)))

    def test_compare_and_set_rejects_stale_status(self):
        db.update(self.vid, "rejected")
        with self.assertRaises(ValueError): db.update(self.vid, "approved_topic", expected_status="idea")
        self.assertEqual(db.get(self.vid)["status"], "rejected")

    def test_bad_video_paths_are_rejected(self):
        for name in ("..", "../escape", "x\\escape", "C:escape", ""):
            with self.assertRaises(ValueError): db.video_dir(name)

    def test_live_legacy_lock_never_expires(self):
        (self.d / ".lock").write_text(json.dumps({"pid": 123, "at": time.time() - 8 * 3600, "stage": "render"}))
        with patch.object(locking, "_pid_alive", return_value=True), self.assertRaises(locking.Busy):
            with locking.video_lock(self.vid): pass

    def test_dead_legacy_lock_is_recovered(self):
        (self.d / ".lock").write_text(json.dumps({"pid": 123, "at": time.time(), "stage": "render"}))
        with patch.object(locking, "_pid_alive", return_value=False):
            with locking.video_lock(self.vid): pass
        self.assertFalse((self.d / ".lock").exists())

    def test_lock_blocks_another_process(self):
        path = self.data / "shared.lock"
        code = "from orchestrator.locking import FileLock,Busy\nimport sys\ntry:\n with FileLock(sys.argv[1]): pass\nexcept Busy: sys.exit(7)"
        with locking.FileLock(path):
            r = subprocess.run([sys.executable, "-B", "-c", code, str(path)], capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 7, r.stderr.decode(errors="replace"))
        r = subprocess.run([sys.executable, "-B", "-c", code, str(path)], capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace"))

    def test_lock_released_after_process_crash(self):
        path = self.data / "crash.lock"
        code = "from orchestrator.locking import FileLock\nimport os,sys\nwith FileLock(sys.argv[1]): os._exit(3)"
        r = subprocess.run([sys.executable, "-B", "-c", code, str(path)], capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 3)
        with locking.FileLock(path): pass

    def test_lock_reentrant_but_blocks_other_thread(self):
        path = self.data / "thread.lock"
        def worker():
            with locking.FileLock(path): pass
        with locking.FileLock(path), locking.FileLock(path):
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                with self.assertRaises(locking.Busy): pool.submit(worker).result()

    def test_manual_stage_respects_video_lock(self):
        (self.d / ".lock").write_text(json.dumps({"pid": 123, "at": 0}))
        fn = Mock()
        with patch.dict(main.STAGE_FN, {"test": fn}), patch.object(locking, "_pid_alive", return_value=True):
            with self.assertRaises(locking.Busy): main.stage("test", self.vid)
        fn.assert_not_called()

    def test_queue_rechecks_status_after_lock(self):
        stale = db.get(self.vid)
        db.update(self.vid, "rejected")
        fn = Mock()
        with patch.dict(main.NEXT, {"idea": fn}, clear=True), patch.object(db, "by_status", return_value=[stale]), patch.object(telegram, "poll"), patch.object(main.upload, "short_comments_tick"), patch.object(main, "_localize_tick"), patch.object(main, "_metrics_tick"), patch.object(main, "_autostart"), patch.object(money, "fal_left") as balance:
            main.run_queue()
        fn.assert_not_called(); balance.assert_not_called()

    def test_review_flag_blocks_paid_assets(self):
        db.update(self.vid, "approved_script", payload={"needs_review": True})
        with patch.object(telegram, "ask_script_review") as ask:
            assets.run(self.vid)
        self.assertEqual(db.get(self.vid)["status"], "scripted")
        ask.assert_called_once()
        db.approve(self.vid)
        self.assertTrue(gates.script_ready(db.get(self.vid)))
        db.update(self.vid, payload={"script": {"script": "Changed text"}})
        self.assertFalse(gates.script_ready(db.get(self.vid)))

    def test_failed_or_missing_gate_blocks_upload(self):
        db.update(self.vid, "approved_final")
        for payload in ({}, {"release_gate": {"ok": False}}):
            db.update(self.vid, payload=payload)
            with self.assertRaises(RuntimeError): gates.require_upload(db.get(self.vid), self.d)

    def test_auto_approval_invalidated_by_artifact_change(self):
        db.update(self.vid, "qc_passed")
        (self.d / "final.mp4").write_bytes(b"first")
        gates.record(self.vid, {"technical": True, "footage": True})
        with patch.object(config, "AUTO_APPROVE", True):
            gates.require_upload(db.get(self.vid), self.d)
            (self.d / "final.mp4").write_bytes(b"replacement")
            with self.assertRaises(RuntimeError): gates.require_upload(db.get(self.vid), self.d)

    def test_explicit_final_override_is_version_bound(self):
        db.update(self.vid, "qc_failed")
        (self.d / "meta.json").write_text("{}")
        db.approve(self.vid)
        gates.require_upload(db.get(self.vid), self.d)
        (self.d / "meta.json").write_text('{"changed":true}')
        with self.assertRaises(RuntimeError): gates.require_upload(db.get(self.vid), self.d)

    def test_ffmpeg_failure_is_not_success(self):
        def failing_run(*args, **kwargs):
            if kwargs.get("check"): raise subprocess.CalledProcessError(1, args[0], stderr="decode failed")
            return subprocess.CompletedProcess(args[0], 1, stderr="decode failed")
        with patch.object(qc.subprocess, "run", side_effect=failing_run), self.assertRaises(subprocess.CalledProcessError):
            qc.tech_check(self.d / "final.mp4", {"duration": 60})

    def test_visual_qc_rejects_incomplete_response(self):
        with patch.object(llm, "ask_vision", return_value={}), self.assertRaises(ValueError):
            qc.visual_check(self.vid, [{"id": "s1"}], b"image")

    def test_preflight_network_failure_blocks(self):
        (self.d / "a.png").write_bytes(b"fixture")
        shots = [{"id": "s1", "type": "broll", "slots": [{"id": "a", "image": "a.png", "role": "main", "kind": "image"}]}]
        with patch.object(preflight, "verify_web_photos"), patch.object(preflight, "_initial_bad", return_value={}), patch.object(preflight, "frame_of", return_value=b"png"), patch.object(preflight, "is_blank", return_value=False), patch.object(preflight, "sheet", return_value=b"sheet"), patch.object(llm, "ask_vision", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "партия"):
                preflight.check(self.d, shots, "text", self.vid, "model", passes=1)

    def test_preflight_exhausted_repairs_block(self):
        with patch.object(preflight, "verify_web_photos"), patch.object(preflight, "_pairs", return_value=[({"id": "s1"}, {"id": "a"})]), patch.object(preflight, "_initial_bad", return_value={1: "broken"}):
            with self.assertRaisesRegex(RuntimeError, "осталось"):
                preflight.check(self.d, [{"id": "s1"}], "text", self.vid, "model", passes=1)

    def test_owner_thumbnail_beats_larger_fallback(self):
        from PIL import Image
        Image.new("RGB", (1280, 720)).save(self.d / "thumb_a.png")
        Image.new("RGB", (2560, 1440)).save(self.d / "thumb_2560.png")
        (self.d / "thumb_a.keep").touch()
        self.assertEqual(thumbcheck.pick(self.d).name, "thumb_a.png")

    def test_missing_owner_thumbnail_does_not_fallback(self):
        (self.d / "thumb_a.keep").touch()
        with self.assertRaises(FileNotFoundError): thumbcheck.pick(self.d)

    def test_budget_excess_stops_before_generation(self):
        with patch.object(config, "BUDGET_USD", 1), self.assertRaises(RuntimeError):
            assets._budget_plan([], 2)

    def test_concurrent_llm_logs_are_unique_and_attributed(self):
        with llm.scope(self.vid):
            with concurrent.futures.ThreadPoolExecutor(10) as pool:
                list(pool.map(lambda _: llm._log("same", "model cost=$0.1000", "prompt", "answer"), range(20)))
        self.assertEqual(len(list((self.data / "llm_log").glob("*.md"))), 20)
        money.reconcile(self.vid)
        self.assertAlmostEqual(db.get(self.vid)["payload"]["cost_usd"], 2.0)

    def test_metrics_partial_snapshots_are_retryable(self):
        c = metrics._table()
        with c:
            for h, complete in ((24, False), (72, True)):
                c.execute("INSERT INTO snapshots VALUES(?,?,?,?)", (self.vid, h, "now", json.dumps({"complete": complete})))
        c.close()
        self.assertEqual(metrics.have(self.vid), {72})

    def test_late_metrics_do_not_count_as_day14(self):
        d = {"complete": True, "public_views": 100, "age_h_real": 360}
        self.assertFalse(metrics.snapshot_quality(d, 336))
        d["age_h_real"] = 340
        self.assertTrue(metrics.snapshot_quality(d, 336))

    def test_even_median(self):
        def row(n):
            return {"n": n, "title": "Example", "series": "A", "d14": {"public": n, "real": n, "min": 1, "subs": 1, "rel_min": 1, "counts": True, "quality": True}}
        with patch.object(metrics, "block_rows", return_value=[row(10), row(20)]):
            self.assertIn("медиана счётчика 15.", metrics.weekly_text())


    def test_full_qc_release_gates(self):
        from orchestrator.stages import footage, publish
        from orchestrator import visual_integrity as vi
        meta = {"titles": ["Example"], "tags": ["history"], "description": "Description"}
        tl = {"duration": 60, "scenes": [{"id": "s1", "type": "broll", "start": 0, "end": 60}]}
        (self.d / "timeline.json").write_text(json.dumps(tl))
        (self.d / "words.json").write_text("[]")
        (self.d / "final.mp4").write_bytes(b"video")
        (self.d / "publish").mkdir()
        for name in ("title.txt", "description.txt", "tags.txt", "thumbnail_2560.jpg"):
            (self.d / "publish" / name).write_text("artifact")
        cases = [(True, True, False, False, True, True), (False, True, False, False, True, False), (True, False, False, False, True, False), (True, True, True, False, True, False), (True, True, False, True, True, False), (True, True, False, False, False, False)]
        for footage_ok, opening_ok, thumb_error, publish_error, archive_ok, expected in cases:
            with self.subTest(footage=footage_ok, opening=opening_ok, thumbnail_error=thumb_error):
                db.update(self.vid, "rendered", payload={"topic": {"format": "story"}, "publish_sha": None})
                (self.d / "opening_check.json").write_text(json.dumps({"ok": opening_ok}))
                if archive_ok:
                    (self.d / "visual_integrity.json").write_text(json.dumps({"version": 1, "ok": True, "key": vi.artifact_key(self.d, tl, "Reviewed text")}))
                    vi.seal_render(self.d, tl, "Reviewed text")
                else:
                    (self.d / "visual_integrity.json").unlink(missing_ok=True)
                with ExitStack() as stack:
                    stack.enter_context(patch.multiple(config, AUTO_APPROVE=True, REQUIRE_FINAL_APPROVAL=False, OPENING_GATE=True))
                    stack.enter_context(patch.object(qc.subprocess, "check_output", return_value=b"60"))
                    stack.enter_context(patch.object(config, "ffprobe", return_value="ffprobe"))
                    stack.enter_context(patch.object(qc, "tech_check", return_value=[]))
                    stack.enter_context(patch.object(qc, "contact_sheet", return_value=b"sheet"))
                    stack.enter_context(patch.object(qc, "visual_check", return_value=[]))
                    stack.enter_context(patch.object(qc, "_meta", return_value=meta))
                    stack.enter_context(patch.object(llm, "ask_json", return_value={"pass": True, "issues": []}))
                    stack.enter_context(patch.object(publish, "run", return_value=meta, side_effect=RuntimeError("offline") if publish_error else None))
                    stack.enter_context(patch.object(thumbcheck, "check", side_effect=RuntimeError("offline") if thumb_error else None, return_value={"ok": True}))
                    stack.enter_context(patch.object(footage, "report", return_value={"ok": footage_ok}))
                    stack.enter_context(patch.object(footage, "line", return_value="Footage report"))
                    stack.enter_context(patch.object(money, "report_html"))
                    stack.enter_context(patch.object(telegram, "send"))
                    stack.enter_context(patch.object(telegram, "ask_final_review"))
                    qc.run(self.vid)
                    v = db.get(self.vid)
                    self.assertEqual(v["payload"]["release_gate"]["ok"], expected)
                    if expected: gates.require_upload(v, self.d)
                    else:
                        self.assertEqual(v["status"], "qc_failed")
                        with self.assertRaises(RuntimeError): gates.require_upload(v, self.d)

    def test_stillcheck_failure_is_a_blocker(self):
        def fake_render(args, **kwargs):
            for frame in args[5:]: (Path(args[4]) / f"still_{frame}.png").write_bytes(b"image")
            return subprocess.CompletedProcess(args, 0)
        with patch.object(stillcheck.subprocess, "run", side_effect=fake_render), patch.object(llm, "ask_vision", side_effect=RuntimeError("offline")):
            result = stillcheck.run(self.d, {"duration": 60}, [])
        self.assertFalse(result["ok"])
        self.assertTrue(all(i["severity"] == "block" for i in result["issues"]))

    def test_render_preserves_previous_file_if_stillcheck_crashes(self):
        from orchestrator.stages import render
        (self.d / "timeline.json").write_text(json.dumps({"format": "story", "duration": 60, "scenes": []}))
        (self.d / "words.json").write_text("[]")
        (self.d / "final.mp4").write_bytes(b"old render")
        with patch.multiple(config, THUMBV_AUTO=False, RESTORE_ARCHIVE=False, SOUND_SCORE=False, STILLCHECK=True), patch.object(render, "guard"), patch.object(stillcheck, "run", side_effect=RuntimeError("offline")), patch.object(render, "_rx") as rx:
            with self.assertRaises(RuntimeError): render.run(self.vid)
        self.assertEqual((self.d / "final.mp4").read_bytes(), b"old render")
        rx.assert_not_called()

    def test_metrics_refresh_preserves_original_public_counter(self):
        db.update(self.vid, "published", youtube_id="youtube-id")
        c = metrics._table()
        with c:
            c.execute("INSERT INTO snapshots VALUES(?,?,?,?)", (self.vid, 24, "original-time", json.dumps({"public_views": 120, "age_h_real": 26, "totals": [], "complete": False})))
        c.close()
        with patch.object(metrics, "AGES_H", [24]), patch.object(metrics, "yt"), patch.object(metrics, "_published_at", return_value=datetime.now(timezone.utc) - timedelta(hours=100)), patch.object(metrics, "_query", return_value={"totals": [{"views": 100}], "errors": ["ctr: unavailable"]}), patch.object(metrics, "public", return_value={"youtube-id": 999}) as public:
            metrics.take()
        result = metrics.rows(self.vid)[0]
        self.assertEqual(result["public_views"], 120)
        self.assertEqual(result["taken"], "original-time")
        self.assertEqual(result["age_h_real"], 26)
        self.assertTrue(result["complete"])
        public.assert_not_called()

    def test_hit_only_marked_after_qualified_and_delivered(self):
        db.update(self.vid, "published", youtube_id="youtube-id")
        for real, delivered, expected in ((100, True, []), (1000, False, []), (1000, True, [2000])):
            with self.subTest(real=real, delivered=delivered):
                client = Mock()
                client.reports.return_value.query.return_value.execute.return_value = {"rows": [[real]]}
                with patch.object(metrics, "block_videos", return_value=[db.get(self.vid)]), patch.object(metrics, "yt", return_value=client), patch.object(metrics, "public", return_value={"youtube-id": 2500}), patch.object(metrics, "_published_at", return_value=datetime.now(timezone.utc) - timedelta(days=10)), patch.object(telegram, "send", return_value={"ok": delivered}) as send:
                    metrics.hit_check()
                self.assertEqual(db.get(self.vid)["payload"].get("hit_told", []), expected)
                if real == 100: send.assert_not_called()

    def test_upload_receipt_survives_lost_database_update(self):
        from orchestrator.stages import upload
        path = self.d / "final.mp4"
        path.write_bytes(b"video")
        client = Mock()
        client.videos.return_value.insert.return_value.next_chunk.return_value = (None, {"id": "persisted-id"})
        with patch.object(upload, "MediaFileUpload"):
            self.assertEqual(upload._once(client, "final.mp4", {}, {"status": {"publishAt": "2026-10-04T21:00:00+00:00"}}, path), "persisted-id")
            restarted = Mock()
            body = {"status": {"publishAt": "new date"}}
            self.assertEqual(upload._once(restarted, "final.mp4", {}, body, path), "persisted-id")
        restarted.videos.assert_not_called()
        self.assertEqual(body["status"]["publishAt"], "2026-10-04T21:00:00+00:00")

    def test_interrupted_upload_never_starts_second_insert(self):
        from orchestrator.stages import upload
        path = self.d / "final.mp4"
        path.write_bytes(b"video")
        client = Mock()
        client.videos.return_value.insert.return_value.next_chunk.side_effect = KeyboardInterrupt()
        with patch.object(upload, "MediaFileUpload"):
            with self.assertRaises(KeyboardInterrupt): upload._once(client, "final.mp4", {}, {}, path)
            restarted = Mock()
            with self.assertRaisesRegex(RuntimeError, "неизвестен"):
                upload._once(restarted, "final.mp4", {}, {}, path)
        restarted.videos.assert_not_called()


    def test_visual_verdict_requires_every_number_and_real_booleans(self):
        from orchestrator import visual_integrity as vi
        good = {"n": 1, "ok": True, "why": "supported by source"}
        self.assertEqual(vi.verdicts({"checks": [good]}, {1})[1], good)
        for result in ({"bad": []}, {"checks": []}, {"checks": [good, good]},
                       {"checks": [{**good, "ok": "false"}]}, {"checks": [{**good, "n": True}]},
                       {"checks": [{**good, "why": ""}]}, {"checks": [{**good, "n": 2}]}):
            with self.subTest(result=result), self.assertRaises(ValueError): vi.verdicts(result, {1})

    def test_visual_intent_survives_candidate_caption_change(self):
        from orchestrator import visual_integrity as vi
        sl = {"caption": "Greyhound annual report", "query": "Greyhound 1945", "visual_intent": None}
        vi.remember_intent(sl, "Greyhound earned $20 million")
        sl["caption"] = "United States Steel report"
        vi.remember_intent(sl, "new narration")
        evidence = json.loads(vi.context(1, {"id": "scene"}, sl, "Greyhound earned $20 million"))
        self.assertEqual(evidence["original_intent"]["caption"], "Greyhound annual report")
        self.assertEqual(evidence["display_caption"], "United States Steel report")
        self.assertIn("$20 million", evidence["narration"])

    def test_clip_verification_fails_closed_on_network_and_partial_answers(self):
        import io
        from PIL import Image
        from orchestrator.stages import archive
        buf = io.BytesIO(); Image.new("RGB", (10, 10)).save(buf, "PNG")
        good = {"period_footage": True, "matches": True, "modern_overlay": False, "dark_or_tiny": False}
        with patch.object(config, "ffmpeg", return_value="ffmpeg"), patch.object(archive.subprocess, "run", return_value=Mock(stdout=buf.getvalue())), patch.object(archive, "_grid", return_value=b"grid"):
            with patch.object(llm, "ask_vision", side_effect=RuntimeError("offline")):
                self.assertIs(archive._verify_clip(self.d / "x.mp4", "text", "q", "cap", "s", self.vid)["ok"], False)
            for result, expected in (({}, False), ({**good, "matches": "false"}, False), ({"period_footage": True, "matches": True}, False), (good, True)):
                with patch.object(llm, "ask_vision", return_value=result):
                    self.assertIs(archive._verify_clip(self.d / "x.mp4", "text", "q", "cap", "s", self.vid)["ok"], expected)

    def test_unverified_caption_is_cleared_not_left_on_new_photo(self):
        from PIL import Image
        from orchestrator.stages import archive
        sl = {"id": "photo", "caption": "Greyhound Annual Report"}
        candidate = {"key": "File:Generic.jpg", "url": "url", "date": "", "desc": "", "artist": "a", "license": "CC"}
        with patch.object(archive, "_commons_url", return_value="url"), patch.object(archive, "_fetch_image", return_value=Image.new("RGB", (20, 20))):
            self.assertTrue(archive._apply_photo(sl, self.d, candidate, {}))
        self.assertIsNone(sl["caption"])
        self.assertIn("description", sl["archive"])

    def test_failed_repair_restores_slot_metadata(self):
        from orchestrator.stages import archive
        sl = {"id": "a", "src": "archive/a.mp4", "kind": "archive", "caption": "Old", "archive": {"key": "old"}}
        before = json.loads(json.dumps(sl))
        with patch.object(archive, "resolve", return_value=False), patch.object(assets, "_image", side_effect=RuntimeError("offline")):
            preflight._replace(sl, self.d, "model", {"usd": 0}, "new concept", 1)
        self.assertEqual(sl, before)

    def test_rejected_unchanged_media_cannot_pass_on_retry(self):
        (self.d / "a.png").write_bytes(b"image")
        shots = [{"id": "s1", "type": "broll", "slots": [{"id": "a", "image": "a.png", "kind": "archive"}]}]
        with patch.object(preflight, "verify_web_photos"), patch.object(preflight, "_initial_bad", return_value={}), patch.object(preflight, "frame_of", return_value=b"png"), patch.object(preflight, "is_blank", return_value=False), patch.object(preflight, "sheet", return_value=b"sheet"), patch.object(preflight, "_reconceive", return_value={}), patch.object(preflight, "_replace"), patch.object(llm, "ask_vision", return_value={"checks": [{"n": 1, "ok": False, "why": "Wrong company"}]}) as judge:
            with self.assertRaisesRegex(RuntimeError, "осталось"):
                preflight.check(self.d, shots, "Greyhound", self.vid, "model", passes=2)
            self.assertEqual(judge.call_count, 1)
            with self.assertRaisesRegex(RuntimeError, "осталось"):
                preflight.check(self.d, shots, "Greyhound", self.vid, "model", passes=1)
            self.assertEqual(judge.call_count, 1)

    def test_visual_receipt_binds_assets_script_and_render(self):
        from orchestrator import visual_integrity as vi
        (self.d / "a.png").write_bytes(b"first")
        (self.d / "final.mp4").write_bytes(b"render")
        tl = {"scenes": [{"id": "s", "image": "a.png"}]}
        receipt = {"version": 1, "ok": True, "key": vi.artifact_key(self.d, tl, "script")}
        (self.d / "visual_integrity.json").write_text(json.dumps(receipt))
        self.assertFalse(vi.approved(self.d, tl, "script", rendered=True))
        vi.seal_render(self.d, tl, "script")
        self.assertTrue(vi.approved(self.d, tl, "script", rendered=True))
        self.assertFalse(vi.approved(self.d, tl, "changed", rendered=True))
        (self.d / "a.png").write_bytes(b"other")  # Same length, different pixels.
        self.assertFalse(vi.approved(self.d, tl, "script", rendered=True))
        (self.d / "a.png").write_bytes(b"first")
        (self.d / "final.mp4").write_bytes(b"replacement")
        self.assertFalse(vi.approved(self.d, tl, "script", rendered=True))

    def test_final_archive_rejection_persists_without_another_paid_judgement(self):
        from orchestrator import visual_integrity as vi
        (self.d / "a.png").write_bytes(b"image")
        tl = {"scenes": [{"id": "s", "image": "a.png", "kind": "archive", "anchor": "Greyhound"}]}
        with patch.object(preflight, "frame_of", return_value=b"png"), patch.object(llm, "ask_vision", return_value={"checks": [{"n": 1, "ok": False, "why": "Wrong report"}]}) as judge:
            for _ in range(2):
                with self.assertRaises(RuntimeError): vi.review(self.d, tl, "Greyhound", self.vid)
            self.assertEqual(judge.call_count, 1)
        self.assertFalse(vi.approved(self.d, tl, "Greyhound"))

    def test_final_review_reuses_unchanged_checks_after_partial_failure(self):
        from orchestrator import visual_integrity as vi
        for name in ("a.png", "b.png"): (self.d / name).write_bytes(name.encode())
        tl = {"scenes": [{"id": n, "image": f"{n}.png", "kind": "archive", "anchor": n} for n in ("a", "b")]}
        good = {"checks": [{"n": 1, "ok": True, "why": "source matches"}]}
        with patch.object(preflight, "frame_of", return_value=b"png"), patch.object(llm, "ask_vision", side_effect=[good, RuntimeError("offline"), good]) as judge:
            with self.assertRaises(RuntimeError): vi.review(self.d, tl, "a b", self.vid)
            vi.review(self.d, tl, "a b", self.vid)
            self.assertEqual(judge.call_count, 3)
        self.assertTrue(vi.approved(self.d, tl, "a b"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
