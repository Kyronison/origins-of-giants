import copy
import unittest
from orchestrator.stages.preflight import _record_reconceived_intent


class ReconceivedIntentTests(unittest.TestCase):
    def test_generated_replacement_records_revision_and_keeps_semantic_constraints(self):
        prior={'query':'Actual 1987 contract','caption':'Eastern contract','person':'Frank Borman','role':'activity'}
        slot={'kind':'image','image':'images/new.png','src':None,'role':'activity','person':'Frank Borman',
              'no_people':True,'prompt':'Hands with a model aircraft, no people or writing','visual_intent':copy.deepcopy(prior)}
        _record_reconceived_intent(slot,'Eastern sold System One in 1987.')
        self.assertEqual(slot['visual_intent_history'][0]['prior'],prior)
        self.assertEqual(slot['visual_intent']['person'],'Frank Borman')
        self.assertEqual(slot['visual_intent']['role'],'activity')
        self.assertEqual(slot['visual_intent']['narration'],'Eastern sold System One in 1987.')
        self.assertTrue(slot['no_people'])
        self.assertIn('not a photograph',slot['visual_intent']['revision'])

    def test_real_archive_and_failed_replacement_cannot_relabel_original_requirement(self):
        for update in ({'kind':'archive','image':'archive/wrong-company.jpg'}, {'kind':'image','image':None}):
            slot={'visual_intent':{'query':'Eastern report'},'prompt':'New illustration',**update}
            before=copy.deepcopy(slot)
            _record_reconceived_intent(slot,'Eastern revenue.')
            self.assertEqual(slot,before)
