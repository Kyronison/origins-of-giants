import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from orchestrator import downloads


class FalRangeDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = patch.object(downloads.config, 'DATA', Path(self.temp.name))
        self.data.start()
        self.addCleanup(self.data.stop)
        self.step = patch.object(downloads, 'STEP', 8)
        self.step.start()
        self.addCleanup(self.step.stop)
        self.payload = bytes(range(37))

    def response(self, url, headers, **kw):
        start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', headers['Range']).groups())
        end = min(end, len(self.payload)-1)
        r = requests.Response()
        r.status_code = 206
        r._content = self.payload[start:end+1]
        r.headers.update({'Content-Range': f'bytes {start}-{end}/{len(self.payload)}', 'ETag': 'stable'})
        return r

    def test_complete_bytes_and_resume_without_new_downloads(self):
        with patch.object(downloads.requests, 'get', side_effect=self.response) as get:
            self.assertEqual(downloads.fal_ranges('https://v3b.fal.media/test.mp3'), self.payload)
            count = get.call_count
            self.assertEqual(downloads.fal_ranges('https://v3b.fal.media/test.mp3'), self.payload)
            self.assertEqual(get.call_count, count)

    def test_short_file_is_not_truncated_or_padded(self):
        self.payload = b'abc'
        with patch.object(downloads.requests, 'get', side_effect=self.response):
            self.assertEqual(downloads.fal_ranges('https://v3b.fal.media/small.mp3'), self.payload)

    def test_changed_etag_cannot_mix_different_resources(self):
        def changed(url, headers, **kw):
            r = self.response(url, headers, **kw)
            if headers['Range'] != 'bytes=0-7': r.headers['ETag'] = 'changed'
            return r
        with patch.object(downloads.requests, 'get', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'changed ETag'):
                downloads.fal_ranges('https://v3b.fal.media/changed.mp3')

    def test_incomplete_range_is_rejected(self):
        def truncated(url, headers, **kw):
            r = self.response(url, headers, **kw)
            r._content = r.content[:-1]
            return r
        with patch.object(downloads.requests, 'get', side_effect=truncated):
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                downloads.fal_ranges('https://v3b.fal.media/truncated.mp3')

    def test_server_ignoring_range_returns_complete_response(self):
        r = requests.Response()
        r.status_code = 200
        r._content = self.payload
        with patch.object(downloads.requests, 'get', return_value=r):
            self.assertEqual(downloads.fal_ranges('https://v3b.fal.media/whole.mp3'), self.payload)
