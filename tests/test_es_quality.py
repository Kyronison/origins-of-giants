"""ES regressions: local fixtures and mocked checks, never production stages."""
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from orchestrator.stages import assets, es_cartoon, es_celebs, es_checks


class FactsForSpanishTests(unittest.TestCase):
    def test_web_research_schema_keeps_claim_quantity_and_provenance(self):
        fact = {"id": "F1", "fact": "Revenue fell to zero in FY2025.",
                "value": 0, "unit": "USD", "date": "2025",
                "source_url": "https://example.test/filing", "source_type": "10-K",
                "quote": "Revenue: $0", "as_of": "FY2025", "estimated": False}
        self.assertEqual(json.loads(es_cartoon._facts({"facts": [fact]})), [fact])

    def test_book_schema_keeps_locator_people_and_zero(self):
        fact = {"id": "B1", "claim": "The founder had no employees.",
                "number": 0, "date": "1998-09", "quote": "", "people": ["Founder"],
                "source_url": "book: Historia — Autor", "source": "Historia — Autor",
                "page": 17, "chapter": "Origen", "verified": False, "value": None}
        self.assertEqual(json.loads(es_cartoon._facts({"facts": [fact]})), [fact])

    def test_mixed_facts_are_not_mutated_or_relabelled(self):
        facts = [{"id": "F1", "fact": "Web fact", "value": False},
                 {"id": "B1", "claim": "Book fact", "number": 0, "pages": [2, 3]}]
        before = json.dumps(facts)
        self.assertEqual(json.loads(es_cartoon._facts({"facts": facts})), facts)
        self.assertEqual(json.dumps(facts), before)

    def test_missing_facts_are_empty_but_malformed_records_are_rejected(self):
        self.assertEqual(es_cartoon._facts({}), "[]")
        for facts in ({"F1": "not a list"}, ["not a record"]):
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                es_cartoon._facts({"facts": facts})


class SpanishVisualCheckTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="es-check-tests-", dir=Path(__file__).resolve().parent)
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "images").mkdir()
        self.shots = [{"id": "p1_001", "image": "images/p1_001.png", "beat": "Una empresa.", "prompt": "A shop."}]
        (self.d / self.shots[0]["image"]).write_bytes(b"original image")
        net = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        net.start(); self.addCleanup(net.stop)

    def run_check(self, ask, signature="rules-v1", shots=None, **kwargs):
        return es_checks.run(self.d, shots or self.shots, "test_qa", signature, ask, **kwargs)

    def test_fail_is_report_only_and_is_cached(self):
        ask = Mock(return_value={"bad": [{"n": 1, "why": "Wrong text"}]})
        report = self.run_check(ask)
        self.assertEqual(report["status"], "FAIL")
        es_checks.require_complete(report, "QA")  # owner's report-only policy
        self.assertEqual(self.run_check(ask)["status"], "FAIL")
        ask.assert_called_once()

    def test_unknown_never_becomes_pass_and_resume_retries_only_unknown(self):
        second = {**self.shots[0], "id": "p1_002", "image": "images/p1_002.png"}
        (self.d / second["image"]).write_bytes(b"other image")
        shots = self.shots + [second]
        def ask(batch):
            if batch[0]["id"] == "p1_002": raise RuntimeError("offline")
            return {"bad": []}
        report = self.run_check(ask, shots=shots, batch_size=1)
        self.assertEqual(report["counts"], {"PASS": 1, "FAIL": 0, "UNKNOWN": 1})
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN"):
            es_checks.require_complete(report, "QA")
        saved = json.loads((self.d / "test_qa.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "UNKNOWN")
        retry = Mock(return_value={"bad": []})
        self.assertEqual(self.run_check(retry, shots=shots)["status"], "PASS")
        retry.assert_called_once()
        self.assertEqual([x["id"] for x in retry.call_args.args[0]], ["p1_002"])

    def test_incomplete_or_malformed_response_is_unknown(self):
        cases = [{}, {"bad": None}, {"bad": [{"n": 2, "why": "out of range"}]},
                 {"bad": [{"n": True, "why": "not an index"}]}, {"bad": [{"n": 1}]}]
        for response in cases:
            with self.subTest(response=response):
                report = self.run_check(Mock(return_value=response))
                self.assertEqual(report["status"], "UNKNOWN")
                with self.assertRaises(RuntimeError): es_checks.require_complete(report, "QA")

    def test_changed_media_context_or_rules_invalidate_verdict(self):
        ask = Mock(return_value={"bad": []})
        self.run_check(ask)
        self.run_check(ask)
        self.assertEqual(ask.call_count, 1)
        (self.d / self.shots[0]["image"]).write_bytes(b"replacement image")
        self.run_check(ask)
        self.shots[0]["beat"] = "Una persona."
        self.run_check(ask)
        self.run_check(ask, signature="rules-v2")
        self.assertEqual(ask.call_count, 4)

    def test_missing_media_is_unknown_without_a_model_request(self):
        self.shots[0]["image"] = "images/missing.png"
        ask = Mock(return_value={"bad": []})
        self.assertEqual(self.run_check(ask)["status"], "UNKNOWN")
        ask.assert_not_called()

    def test_image_qa_records_unknown_instead_of_empty_bad(self):
        with patch.object(es_cartoon, "_sheet", return_value=b"sheet"), \
                patch.object(es_cartoon.llm, "ask_vision", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "UNKNOWN"):
                es_cartoon._check_images("test", self.d, self.shots)
        report = json.loads((self.d / "es_image_qa.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "UNKNOWN")

    def _draw(self, prompt, d, sid, model, **kwargs):
        image = f"images/{sid}.png"
        (d / image).write_bytes(sid.encode())
        return image

    def test_celebrity_last_replacements_are_checked_but_fail_does_not_block(self):
        bad = {"bad": [{"n": 1, "who": "Unrelated person", "why": "Not part of the story"}]}
        with patch.object(es_celebs.db, "video_dir", return_value=self.d), \
                patch.object(es_celebs.db, "get", return_value={"payload": {"topic": {"company": "Example"}}}), \
                patch.object(es_celebs, "_sheet", return_value=b"sheet"), \
                patch.object(es_celebs.llm, "ask_vision", return_value=bad) as vision, \
                patch.object(assets, "_image", side_effect=self._draw) as draw:
            self.assertEqual(es_celebs.clean("test", self.shots), 2)
        self.assertEqual(draw.call_count, 2)
        self.assertEqual(vision.call_count, 3)  # original, c1, final c2
        self.assertEqual(self.shots[0]["image"], "images/p1_001_c2.png")
        report = json.loads((self.d / "es_celebrity_qa.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["items"][0]["image"], self.shots[0]["image"])

    def test_celebrity_unknown_resume_reuses_replacement_without_purchase(self):
        bad = {"bad": [{"n": 1, "who": "Unrelated person", "why": "Not part of the story"}]}
        original = dict(self.shots[0])
        with patch.object(es_celebs.db, "video_dir", return_value=self.d), \
                patch.object(es_celebs.db, "get", return_value={"payload": {"topic": {"company": "Example"}}}), \
                patch.object(es_celebs, "_sheet", return_value=b"sheet"), \
                patch.object(es_celebs.llm, "ask_vision", side_effect=[bad, RuntimeError("offline"), {"bad": []}]) as vision, \
                patch.object(assets, "_image", side_effect=self._draw) as draw:
            with self.assertRaisesRegex(RuntimeError, "UNKNOWN"):
                es_celebs.clean("test", self.shots)
            resumed = [original]
            es_celebs.clean("test", resumed)
        self.assertEqual(draw.call_count, 1)
        self.assertEqual(vision.call_count, 3)
        self.assertEqual(resumed[0]["image"], "images/p1_001_c1.png")
        report = json.loads((self.d / "es_celebrity_qa.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS")

    def test_storyboard_error_waits_for_voice_without_masking_original_error(self):
        voice_started = threading.Event(); release_voice = threading.Event()
        voice_finished = threading.Event(); board_failed = threading.Event(); stage_done = threading.Event()
        errors = []
        def voice(*args):
            voice_started.set()
            release_voice.wait(3)
            voice_finished.set()
        def beats(*args):
            voice_started.wait(3)
            board_failed.set()
            raise ValueError("original storyboard failure")
        def run():
            try: es_cartoon.assets("test")
            except Exception as exc: errors.append(exc)
            finally: stage_done.set()
        value = {"payload": {"topic": {"company": "Example"},
                              "script": {"parts": ["Una empresa."], "years": ["1990"], "names": ["Origen"]}}}
        with patch.object(es_cartoon.db, "video_dir", return_value=self.d), \
                patch.object(es_cartoon.db, "get", return_value=value), \
                patch.object(es_cartoon.config, "ES_VOICE_ID", ""), \
                patch.object(es_cartoon, "_beats", side_effect=beats), \
                patch.object(assets, "_voice", side_effect=voice):
            worker = threading.Thread(target=run)
            worker.start()
            try:
                self.assertTrue(board_failed.wait(3))
                self.assertFalse(stage_done.wait(0.05))
            finally:
                release_voice.set()
                worker.join(3)
        self.assertTrue(voice_finished.is_set())
        self.assertTrue(stage_done.is_set())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertEqual(str(errors[0]), "original storyboard failure")


if __name__ == "__main__":
    unittest.main()
