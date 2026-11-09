import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config, db, gates, money
from orchestrator.stages import story_assets as sa, opening


class OpeningPurchaseGateTests(unittest.TestCase):
    def test_failed_actual_voice_opening_stops_before_purchasing_media(self):
        payload = {'script': {'script': 'An opening.', 'parts': ['An opening.'],
            'shots': [{'id': 'first', 'type': 'broll', 'slots': [
                {'id': 'first_s1', 'source': 'image', 'prompt': 'Restaurant'}]}]}}
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(gates, 'require_script', return_value=True), \
                 patch.object(db, 'get', return_value={'payload': payload}), \
                 patch.object(db, 'video_dir', return_value=Path(temp)), \
                 patch.object(db, 'update') as update, \
                 patch.object(money, 'spent', return_value=0), \
                 patch.object(config, 'ERA_FOOTAGE', False), \
                 patch.object(config, 'OPENING_GATE', True), \
                 patch.object(sa.archive, 'reset'), \
                 patch.object(sa.A, '_voice'), \
                 patch.object(sa.P, 'ensure', return_value=[]), \
                 patch.object(opening, 'check', return_value={'ok': False}), \
                 patch.object(sa, '_resolve_slots') as resolve, \
                 patch.object(sa.A, '_thumb') as thumb:
                with self.assertRaisesRegex(RuntimeError, 'до закупки кадров'):
                    sa.run('test-video')
                resolve.assert_not_called()
                thumb.assert_not_called()
                self.assertTrue(update.call_args.kwargs['payload']['opening_needs_review'])


if __name__ == '__main__':
    unittest.main()
