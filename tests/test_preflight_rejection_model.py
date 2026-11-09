import unittest
from unittest.mock import patch
from orchestrator import config
from orchestrator.stages import preflight

class RejectionModelTest(unittest.TestCase):
    def test_changed_reviewer_requires_fresh_assessment_of_same_media(self):
        sc={'id':'one','type':'broll','anchor':'A calculator measures costs'}
        sl={'id':'one_s1','kind':'image','image':'images/one.png','prompt':'a calculator','role':'main'}
        with patch.object(config,'LLM_MODEL_VISION','reviewer-one'):
            old=preflight.rejection_context_key(sc,sl,'A calculator measures costs.')
            self.assertEqual(old,preflight.rejection_context_key(sc,sl,'A calculator measures costs.'))
        with patch.object(config,'LLM_MODEL_VISION','reviewer-two'):
            new=preflight.rejection_context_key(sc,sl,'A calculator measures costs.')
        self.assertNotEqual(old,new)
