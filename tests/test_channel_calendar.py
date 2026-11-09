"""Channel-calendar regressions; only in-memory SQLite and mocked uploads."""
import json
from pathlib import Path
import socket
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from orchestrator import gates
from orchestrator.stages import upload


class Clock(datetime):
    moment = datetime(2026, 10, 14, 18, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.moment.astimezone(tz)


class UploadCaptured(Exception):
    pass


class ChannelCalendar(unittest.TestCase):
    def setUp(self):
        self.rows = []
        Clock.moment = datetime(2026, 10, 14, 18, tzinfo=timezone.utc)
        for p in (
            patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")),
            patch.object(upload.db, "conn", side_effect=self.connection),
            patch.object(upload.db, "update", side_effect=AssertionError("Database mutations forbidden")),
            patch.object(upload, "datetime", Clock),
            patch.multiple(upload.config, PUBLISH_HOUR_ET=17, PUBLISH_WEEKDAYS_ET=[0, 3],
                           PUBLISH_NOT_BEFORE="", UPLOAD_MODE="api"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def connection(self):
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE videos(id TEXT, status TEXT, payload TEXT, publish_at TEXT)")
        c.executemany("INSERT INTO videos VALUES(?,?,?,?)", self.rows)
        return c

    def add(self, vid="english", status="uploaded", payload=None, at="2026-10-15T15:00:00+00:00"):
        self.rows.append((vid, status, json.dumps(payload or {}), at))

    def test_new_spanish_states_do_not_reserve_english_day(self):
        for state in ("es_topic", "es_scripted", "es_assets", "es_ready", "es_uploaded", "es_qc_failed"):
            with self.subTest(state=state):
                self.rows.clear()
                self.add("2026-10-13-amzn-es-historia-completa", state)
                self.assertEqual(upload.next_slot().isoformat(), "2026-10-15T21:00:00+00:00")

    def test_legacy_localizations_do_not_reserve_english_day(self):
        for vid, state in (("old-apple__es", "uploaded"), ("old-apple", "localized"),
                           ("old-apple", "localized_uploaded"), ("old-apple__fr", "localized_uploaded")):
            with self.subTest(vid=vid, state=state):
                self.rows.clear()
                self.add(vid, state)
                self.assertEqual(upload.next_slot().isoformat(), "2026-10-15T21:00:00+00:00")

    def test_explicit_foreign_metadata_cannot_leak_into_english_calendar(self):
        for payload in ({"lang": "es"}, {"lang": "fr"}, {"script": {"lang": "es"}},
                        {"topic": {"lang_target": "es-MX"}}, {"topic": {"es_only": True}},
                        {"es_only_skip": True}):
            with self.subTest(payload=payload):
                self.rows.clear()
                self.add("legacy", "uploaded", payload)
                self.assertEqual(upload.next_slot().isoformat(), "2026-10-15T21:00:00+00:00")

    def test_real_english_conflicts_remain_reserved(self):
        for vid, payload in (("legacy-english", {}), ("news_es", {}),
                             ("english", {"lang": "en-US", "script": {"lang": "en"}})):
            with self.subTest(vid=vid, payload=payload):
                self.rows.clear()
                self.add(vid, payload=payload)
                self.add("spanish", "es_uploaded", at="2026-10-19T15:00:00+00:00")
                self.assertEqual(upload.next_slot().isoformat(), "2026-10-19T21:00:00+00:00")

    def test_damaged_legacy_metadata_does_not_free_an_english_slot(self):
        self.rows.append(("english", "uploaded", "not json", "2026-10-15T21:00:00+00:00"))
        self.assertEqual(upload.next_slot().isoformat(), "2026-10-19T21:00:00+00:00")

    def test_default_lead_and_not_before_are_preserved(self):
        Clock.moment = datetime(2026, 10, 15, 14, tzinfo=timezone.utc)
        self.assertEqual(upload.next_slot().isoformat(), "2026-10-19T21:00:00+00:00")
        with patch.object(upload.config, "PUBLISH_NOT_BEFORE", "2026-10-20T00:00:00+00:00"):
            self.assertEqual(upload.next_slot(lead_h=1).isoformat(), "2026-10-22T21:00:00+00:00")

    def test_current_et_hour_and_dst_policy_are_preserved(self):
        Clock.moment = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
        self.assertEqual(upload.next_slot().isoformat(), "2026-11-02T22:00:00+00:00")

    def capture_run(self, now, mode="api"):
        Clock.moment = now
        video = {"id": "redlobster", "payload": {}, "youtube_id": None, "publish_at": None}
        captured = {}

        def once(client, key, done, body, path):
            captured["slot"] = body["status"]["publishAt"]
            raise UploadCaptured

        def manual(vid, directory, meta, slot):
            captured["slot"] = slot.isoformat()
            raise UploadCaptured

        with patch.object(upload.db, "get", return_value=video), \
             patch.object(upload.db, "video_dir", return_value=Path("unused-calendar-test")), \
             patch.object(upload.config, "read", return_value=json.dumps({"titles": ["Red Lobster"], "description": "", "tags": []})), \
             patch.object(upload.config, "UPLOAD_MODE", mode), \
             patch.object(gates, "require_upload"), patch.object(upload, "_guard"), \
             patch.object(upload, "yt", return_value=Mock()), \
             patch.object(upload, "_once", side_effect=once), patch.object(upload, "_manual", side_effect=manual):
            with self.assertRaises(UploadCaptured):
                upload.run("redlobster")
        return captured["slot"]

    def test_approved_upload_with_seven_hours_left_uses_current_slot(self):
        self.add("amazon", "es_uploaded")
        slot = self.capture_run(datetime(2026, 10, 15, 14, tzinfo=timezone.utc))
        self.assertEqual(slot, "2026-10-15T21:00:00+00:00")

    def test_automatic_upload_keeps_one_hour_safety_margin(self):
        slot = self.capture_run(datetime(2026, 10, 15, 20, 30, tzinfo=timezone.utc))
        self.assertEqual(slot, "2026-10-19T21:00:00+00:00")

    def test_manual_preparation_keeps_twelve_hour_lead(self):
        slot = self.capture_run(datetime(2026, 10, 15, 14, tzinfo=timezone.utc), mode="manual")
        self.assertEqual(slot, "2026-10-19T21:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
