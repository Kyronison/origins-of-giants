import copy,unittest
from orchestrator.stages.preflight import rejection_context_key

class RejectionContextTest(unittest.TestCase):
 def test_same_evidence_keeps_rejection_and_changed_requirement_requires_review(self):
  scene={'id':'scene','anchor':'In 1997 Esther spoke','data':{}}
  slot={'id':'portrait','role':'portrait','person':'Esther Snyder','image':'same.jpg',
   'caption':'Esther Snyder, 1997','visual_intent':{'person':'Esther Snyder','caption':'1997 interview'},
   'archive':{'description':'Attributed historical portrait','date':None}}
  script='In 1997 Esther spoke to a reporter.'
  original=rejection_context_key(scene,slot,script)
  self.assertEqual(original,rejection_context_key(copy.deepcopy(scene),copy.deepcopy(slot),script))
  revised=copy.deepcopy(slot);revised['caption']='Esther Snyder, historical portrait'
  revised['visual_intent']['caption']='Historical portrait illustration, not interview footage'
  self.assertNotEqual(original,rejection_context_key(scene,revised,script))
  changed=copy.deepcopy(slot);changed['archive']['description']='A different person'
  self.assertNotEqual(original,rejection_context_key(scene,changed,script))
