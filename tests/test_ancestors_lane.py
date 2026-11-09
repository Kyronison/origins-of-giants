"""Offline regressions for third-channel isolation, authorization and budgets."""
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from orchestrator import config, db, spend, ancestors_budget as budget
from orchestrator.ancestors_profile import CHANNEL_ID
from orchestrator.stages import ancestors_cartoon as anc, ancestors_youtube as youtube


class AncestorsLane(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "ancestors"
        self.shared = self.root / "shared"
        # Public test fixtures must not depend on private production seed files.
        fixture_seed = Path(__file__).resolve().parent / "fixtures" / "ancestors_pilot"
        for guard in (
            patch.object(anc, "SEED", fixture_seed),
            patch.dict(os.environ, {"CHANNEL_PROFILE": "ancestors", "SPEND_LEDGER_PATH": str(self.shared / "spend.sqlite3"),
                                    "SHARED_PIPELINE_DB": str(self.shared / "pipeline.db"),
                                    "SPEND_VIDEO_LIMIT": "25", "SPEND_MONTH_LIMIT": "500"}),
            patch.multiple(config, DATA=self.data, VIDEOS=self.data / "videos", RENDER_TMP=self.data / "render"),
            patch.object(socket.socket, "connect", side_effect=AssertionError("No network in tests")),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def pilot(self):
        return anc.start()

    def fake_youtube(self, channel=CHANNEL_ID):
        y = Mock()
        y.channels().list().execute.return_value = {"items": [{"id": channel, "snippet": {"title": "Ordinary Ancestors"}}]}
        y.videos().list().execute.return_value = {"items": [{"snippet": {"channelId": channel}, "status": {"privacyStatus": "private"}}]}
        y.videos().insert().next_chunk.return_value = (None, {"id": "private-pilot"})
        y.reset_mock()
        return y

    def ready(self):
        vid = self.pilot()
        db.update(vid, "anc_ready", payload={"tech": [], "visual_qa": {"status": "PASS"}})
        d = db.video_dir(vid)
        (d / "publish").mkdir()
        (d / "publish/title.txt").write_text(anc.TITLE, encoding="utf-8")
        (d / "publish/description.txt").write_text("Reconstruction", encoding="utf-8")
        with (d / "final.mp4").open("wb") as f:
            f.truncate(20_000_001)
        return vid

    def test_process_bootstrap_changes_only_third_profile(self):
        env = dict(os.environ, ANCESTORS_DATA_DIR=str(self.data), ANCESTORS_SHARED_DATA=str(self.shared))
        code = ("from orchestrator.ancestors_profile import activate; activate(); "
                "from orchestrator import config,spend; import json; "
                "print(json.dumps([str(config.DATA),str(spend._path()),config.AUTO_PIPELINE,config.ES_CARTOON,config.SHORTS_PER_VIDEO]))")
        r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        result = json.loads(r.stdout)
        self.assertEqual(Path(result[0]), self.data)
        self.assertEqual(Path(result[1]), self.shared / "spend.sqlite3")
        self.assertEqual(result[2:], [False, False, 0])
        self.assertFalse((self.shared / "pipeline.db").exists())

    def test_start_is_idempotent_first_only_and_separate_database(self):
        one, two = self.pilot(), self.pilot()
        self.assertEqual(one, two)
        self.assertEqual(db.get(one)["status"], "anc_topic")
        self.assertTrue((self.data / "pipeline.db").exists())
        self.assertFalse((self.shared / "pipeline.db").exists())
        self.assertEqual(youtube.token_path(), self.data / "youtube_token_ancestors.json")
        altered = dict(db.get(one)["payload"]["research"])
        altered["extra"] = "new unsupported material"
        db.update(one, payload={"research": altered})
        with self.assertRaisesRegex(ValueError, "Research changed"):
            anc.validate_video(one)

    def test_wrong_channel_stops_before_insert(self):
        vid = self.ready()
        y = self.fake_youtube("wrong-channel")
        with patch.object(youtube, "client", return_value=y):
            with self.assertRaisesRegex(RuntimeError, "Wrong YouTube channel"):
                youtube.upload_private(vid)
        y.videos().insert.assert_not_called()
        self.assertEqual(db.get(vid)["status"], "anc_ready")

    def test_private_upload_receipt_prevents_duplicate(self):
        vid = self.ready()
        y = self.fake_youtube()
        with patch.object(youtube, "client", return_value=y):
            self.assertEqual(youtube.upload_private(vid), "private-pilot")
            self.assertEqual(youtube.upload_private(vid), "private-pilot")
        self.assertEqual(y.videos().insert.call_count, 1)
        body = y.videos().insert.call_args.kwargs["body"]
        y.videos().insert.call_args.kwargs["media_body"]._fd.close()
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertNotIn("publishAt", body["status"])
        self.assertIsNone(db.get(vid)["publish_at"])

    def test_ambiguous_upload_is_not_retried(self):
        vid = self.ready()
        (db.video_dir(vid) / "final.mp4.upload.json").write_text('{"state":"pending"}')
        y = self.fake_youtube()
        with patch.object(youtube, "client", return_value=y):
            with self.assertRaises(RuntimeError):
                youtube.upload_private(vid)
        y.videos().insert.assert_not_called()

    def test_auth_wrong_channel_does_not_replace_existing_token(self):
        path = youtube.token_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("previous-token", encoding="utf-8")
        flow = Mock()
        flow.run_local_server.return_value = SimpleNamespace(to_json=lambda: "new-token")
        y = self.fake_youtube("wrong-channel")
        with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", return_value=flow), \
             patch("orchestrator.stages.upload.gbuild", return_value=y), \
             patch.dict(os.environ, {"YOUTUBE_CLIENT_SECRET_FILE": "dummy.json"}):
            with self.assertRaisesRegex(RuntimeError, "Wrong YouTube channel"):
                youtube.auth()
        self.assertEqual(path.read_text(), "previous-token")
        self.assertFalse(flow.run_local_server.call_args.kwargs["open_browser"])

    def test_budget_reservation_atomic_across_workers(self):
        spend.ensure_baseline("pilot", 24.7)
        at = spend.Attribution("pilot", "images")
        def request(_):
            try:
                return spend._begin("fal", "test", {}, at)
            except budget.BudgetStop:
                return None
        with patch.object(budget, "reserve_amount", return_value=0.2):
            with ThreadPoolExecutor(8) as pool:
                attempts = list(pool.map(request, range(8)))
        self.assertEqual(sum(x is not None for x in attempts), 1)
        with closing(spend._connect()) as c:
            self.assertLessEqual(budget.totals(c, "pilot")["video_reserved_usd"], 25)
        self.assertFalse((self.data / "spend.sqlite3").exists())

    def test_shared_month_counts_other_channels_and_blocks_before_call(self):
        spend.ensure_baseline("original-en", 490)
        spend.ensure_baseline("original-es", 9.9)
        spend.ensure_baseline("pilot", 0)
        paid = Mock()
        with patch.object(budget, "reserve_amount", return_value=0.2), \
             patch.object(spend, "current", return_value=spend.Attribution("pilot", "script")):
            with self.assertRaisesRegex(budget.BudgetStop, "monthly"):
                spend.openrouter_call(paid, model="example", arguments={})
        paid.assert_not_called()

    def test_unknown_price_refuses_payment_and_confirmed_releases_reserve(self):
        with self.assertRaises(budget.BudgetStop):
            budget.reserve_amount("fal", "unknown", {}, None)
        spend.ensure_baseline("pilot", 0)
        with patch.object(budget, "reserve_amount", return_value=2):
            attempt = spend._begin("openrouter", "test", {}, spend.Attribution("pilot", "script"))
        with closing(spend._connect()) as c:
            self.assertEqual(budget.totals(c, "pilot")["video_reserved_usd"], 2)
        spend._update(attempt, state="succeeded", confirmed_usd=0.25)
        with closing(spend._connect()) as c:
            self.assertEqual(budget.totals(c, "pilot")["video_reserved_usd"], 0.25)

    def test_source_script_contract_and_no_automatic_upload(self):
        script = anc._script_shape(anc._json(anc.SEED / "script.json"))
        self.assertEqual(len(script["parts"]), 5)
        self.assertEqual(set(anc.NEXT), {"anc_topic", "anc_scripted", "anc_assets"})
        self.assertNotIn("anc_ready", anc.NEXT)

    def test_complete_offline_pilot_and_cached_resume_stops_at_ready(self):
        from PIL import Image
        from orchestrator.stages import assets, es_cartoon, sound, qc
        vid = self.pilot()
        image_calls = []
        def ask(prompt, **kwargs):
            if "Storyboard Ordinary Ancestors" in prompt:
                n = int(re.search(r"exactly (\d+) unique", prompt).group(1))
                return {"shots": [{"n": k, "prompt": "An ordinary round headed person beside the central hearth in an imagined simple prehistoric shelter, ink drawing on warm paper"}
                                  for k in range(1, n+1)]}
            return {"fixes": [], "unresolved": []}
        def voice(text, d, parts):
            (d / "voice.mp3").write_bytes(b"test voice")
            anc._save(d / "words.json", [{"w": word, "s": i*0.4, "e": (i+1)*0.4} for i, word in enumerate(text.split())])
        def draw(prompt, d, sid, model, **kwargs):
            image_calls.append(sid)
            (d / "images").mkdir(exist_ok=True)
            Image.new("RGB", (64, 36), "beige").save(d / "images" / (sid + ".png"))
            return "images/" + sid + ".png"
        def check(vid, d, shots, research):
            return {"status": "PASS", "counts": {"PASS": len(shots), "FAIL": 0, "UNKNOWN": 0},
                    "items": [{"id": x["id"], "status": "PASS", "issues": []} for x in shots]}
        def render(d, spec, out):
            out.write_bytes(b"test final")
        def master(src, dst):
            dst.write_bytes(src.read_bytes())
        with patch.object(anc.llm, "ask_json", side_effect=ask), \
             patch.object(assets, "_voice", side_effect=voice), \
             patch.object(assets, "_image", side_effect=draw), \
             patch.object(anc, "_check_images", side_effect=check), \
             patch.object(es_cartoon, "_ffmpeg_render", side_effect=render) as renders, \
             patch.object(sound, "master", side_effect=master), \
             patch.object(qc, "tech_check", return_value=[]), \
             patch.object(youtube, "upload_private", side_effect=AssertionError("No implicit upload")):
            anc.run_queue()
            self.assertEqual(db.get(vid)["status"], "anc_scripted")
            anc.run_queue()
            self.assertEqual(db.get(vid)["status"], "anc_assets")
            count = len(image_calls)
            anc.assets(vid)
            self.assertEqual(len(image_calls), count)
            anc.run_queue()
            self.assertEqual(db.get(vid)["status"], "anc_ready")
            anc.run_queue()
            anc.render(vid)
            self.assertEqual(renders.call_count, 1)
            self.assertIsNone(db.get(vid)["youtube_id"])


if __name__ == "__main__":
    unittest.main()
