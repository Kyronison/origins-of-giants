import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from orchestrator.tools.eastern_editorial_gate import install
from orchestrator.stages import preflight,archive

class EditorialMediaTests(unittest.TestCase):
    def test_exact_manual_rejection_cannot_be_overruled_by_empty_automatic_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp);(w/'archive').mkdir();p=w/'archive/source.jpg';p.write_bytes(b'wrong-company')
            report={'findings':[{'path':'archive/source.jpg','media_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'decision':'reject','why':'Wrong company'}]}
            (w/'editorial-source-findings.json').write_text(json.dumps(report))
            pairs=[({'id':'sc'},{'image':'archive/source.jpg'})]
            with patch.object(preflight,'_initial_bad',return_value={}),patch.object(archive,'_apply_photo'):
                install(w)
                self.assertIn(1,preflight._initial_bad(pairs,w))
                (w/'archive/renamed.jpg').write_bytes(p.read_bytes())
                self.assertIn(1,preflight._initial_bad([({'id':'other'},{'image':'archive/renamed.jpg'})],w))
                # A genuinely new file is judged normally; the old rejected byte receipt cannot reject it by filename.
                p.write_bytes(b'correct-company')
                self.assertEqual(preflight._initial_bad(pairs,w),{})

    def test_wrong_photo_alias_is_rejected_before_selection_and_previous_media_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp);(w/'archive').mkdir();p=w/'archive/source.jpg';p.write_bytes(b'previous-good-photo')
            (w/'editorial-source-findings.json').write_text(json.dumps({'findings':[{
                'path':'archive/old-name.jpg','media_sha256':hashlib.sha256(b'wrong-company').hexdigest(),
                'decision':'reject','why':'Wrong company'}]}))
            def apply(slot,d,candidate,result):
                p.write_bytes(b'wrong-company');slot.update(image='archive/source.jpg',caption='new candidate',archive={'key':candidate['key']});return True
            slot={'id':'scene','image':'archive/source.jpg','caption':'previous good','archive':{'key':'good-source'}}
            with patch.object(preflight,'_initial_bad',return_value={}),patch.object(archive,'_apply_photo',side_effect=apply):
                install(w)
                self.assertFalse(archive._apply_photo(slot,w,{'key':'another-alias-for-bad-photo'},{}))
                self.assertEqual(slot['caption'],'previous good')
                self.assertEqual(slot['archive']['key'],'good-source')
                self.assertEqual(p.read_bytes(),b'previous-good-photo')
                self.assertIn('another-alias-for-bad-photo',slot['_tried'])

if __name__=='__main__':unittest.main()
