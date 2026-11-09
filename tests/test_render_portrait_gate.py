import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from orchestrator.stages import render,preflight

class RenderPortraitGateTests(unittest.TestCase):
    def test_unexpected_verification_error_blocks_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(preflight,'verify_portraits',side_effect=ValueError('invalid media')):
                with self.assertRaisesRegex(RuntimeError,'invalid media'):
                    render._portrait_guard(Path(tmp),{'scenes':[]})

    def test_network_error_remains_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(preflight,'verify_portraits',side_effect=RuntimeError('проверка портретов не завершена: offline')):
                with self.assertRaisesRegex(RuntimeError,'offline'):
                    render._portrait_guard(Path(tmp),{'scenes':[]})

if __name__=='__main__':unittest.main()
