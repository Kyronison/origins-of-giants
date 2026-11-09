import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from orchestrator.locking import FileLock
from orchestrator.public_media import public_view
from orchestrator.stages import render


class PublicMediaTests(unittest.TestCase):
    def test_held_execution_lock_and_existing_render_are_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'video';source.mkdir()
            (source/'voice.mp3').write_bytes(b'voice')
            (source/'words.json').write_bytes(b'[]')
            (source/'portrait.jpg').write_bytes(b'portrait')
            (source/'final.mp4').write_bytes(b'delivered')
            with FileLock(source/'.execution.lock','public-media-test'):
                with public_view(source,{'timeline':{'image':'portrait.jpg'}},root/'tmp') as public:
                    self.assertEqual({p.name for p in public.iterdir()}, {'voice.mp3','words.json','portrait.jpg'})
                    self.assertEqual((public/'portrait.jpg').read_bytes(),b'portrait')
                self.assertFalse(public.exists())
                self.assertTrue((source/'.execution.lock').exists())
            self.assertEqual((source/'final.mp4').read_bytes(), b'delivered')

    def test_renderer_keeps_props_receipt_and_uses_separate_public_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'video';source.mkdir()
            (source/'logo.svg').write_bytes(b'<svg/>')
            props={'timeline':{'voice':False},'logo':'logo.svg'};seen=[]
            def run(args,**kwargs):
                public=Path(args[args.index('--public-dir')+1]);seen.append(public)
                self.assertNotEqual(public,source)
                self.assertEqual((public/'logo.svg').read_bytes(),b'<svg/>')
                self.assertFalse((public/'.execution.lock').exists())
                self.assertEqual(Path(args[args.index('--props')+1]),source/'props_Thumb.json')
            with FileLock(source/'.execution.lock','render-public-test'), patch.object(render.config,'RENDER_TMP',root/'tmp'), patch.object(render.config,'REMOTION',root), patch.object(render.config,'npx',return_value='npx'), patch.object(render.subprocess,'run',side_effect=run):
                render._rx('still','Thumb',root/'thumb.png',props,source)
            self.assertEqual(len(seen),1)
            self.assertFalse(seen[0].exists())
            self.assertTrue((source/'props_Thumb.json').exists())


if __name__=='__main__':unittest.main()
