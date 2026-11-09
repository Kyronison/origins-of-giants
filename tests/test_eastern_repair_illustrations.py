import tempfile,unittest,sys,copy
from pathlib import Path
from unittest.mock import patch
from orchestrator.tools.eastern_repair_illustrations import install,saved_plan
from orchestrator import llm
from orchestrator.stages import preflight

class EasternRepairIllustrationsTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr,preflight,'_reconceive',preflight._reconceive)
        self.addCleanup(setattr,llm,'ask_json',llm.ask_json)
    def test_failed_purchase_preserves_original_source_and_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot={'id':'s','kind':'archive','image':'old.jpg','src':None,'archive':{'key':'source'},'credit':'original','visual_intent':{'query':'specific company'}}
            old=copy.deepcopy(slot)
            with patch.object(preflight,'_replace',return_value=None):
                install();preflight._replace(slot,Path(tmp),'model',{},'objects',1)
            self.assertEqual(slot,old)

    def test_success_is_labelled_and_remains_pending_a_real_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'new.png').write_bytes(b'new media')
            def purchased(candidate,*args):candidate.update(image='new.png',kind='image',prompt=args[3])
            slot={'id':'s','kind':'archive','image':'old.jpg','archive':{'key':'wrong company'},'credit':'old','visual_intent':{'query':'required company','narration':'reviewed'}}
            with patch.object(preflight,'_replace',side_effect=purchased):
                install();preflight._replace(slot,d,'model',{},'workshop',1,ctx='unchanged narration')
            self.assertEqual(slot['caption'],'Illustration');self.assertTrue(slot['no_people'])
            self.assertNotIn('archive',slot);self.assertNotIn('credit',slot)
            self.assertEqual(slot['visual_intent_history'][0]['prior']['query'],'required company')
            self.assertEqual(slot['visual_intent']['narration'],'unchanged narration')
            self.assertNotIn('ok',slot);self.assertNotIn('portrait_ok',slot)

    def test_named_portrait_keeps_normal_attribution_path(self):
        with patch.object(preflight,'_replace') as original:
            install();preflight._replace({'kind':'archive','role':'portrait'},Path('.'),'model',{},'portrait',1)
            original.assert_called_once()

    def test_primary_document_cannot_turn_into_fabricated_paper(self):
        with patch.object(preflight,'_replace') as original:
            install();preflight._replace({'kind':'archive','image':'primary_sources/genuine.png'},Path('.'),'model',{},'document',1)
            original.assert_called_once()

    def test_saved_plan_requires_identical_prompt_model_settings_and_complete_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);p=folder/'20261006_reconceive1_episode.md'
            p.write_text('# checker effort=low max_tokens=6000 finish=stop tokens=1->1\n\n## prompt\n\nexact request\n\n## answer\n\n{"shots":[{"id":"s","prompt":"empty hangar"}]}',encoding='utf-8')
            self.assertEqual(saved_plan(folder,'exact request','checker',6000,'low')['shots'][0]['id'],'s')
            for args in [('changed request','checker',6000,'low'),('exact request','other',6000,'low'),('exact request','checker',4000,'low')]:
                self.assertIsNone(saved_plan(folder,*args))
            p.write_text(p.read_text().replace('finish=stop','finish=length'),encoding='utf-8')
            self.assertIsNone(saved_plan(folder,'exact request','checker',6000,'low'))

if __name__=='__main__':unittest.main()
