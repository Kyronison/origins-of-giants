import re,unittest
from unittest.mock import patch
from orchestrator.stages import preflight

class ReconceiveBatchTest(unittest.TestCase):
    def rows(self,n):
        return [({'id':f's{i}','type':'broll','anchor':'Costs kept rising'},
                 {'id':f's{i}_s1','prompt':'1980s aircraft equipment','no_people':True},'wrong object') for i in range(n)]
    def test_complete_small_batches_use_bounded_low_reasoning(self):
        calls=[]
        def ask(prompt,**kw):
            ids=re.findall(r'^id: (\S+)',prompt,re.M)
            calls.append((ids,kw))
            return {'shots':[{'id':sid,'prompt':'1980s unmarked aircraft tool cart, no people'} for sid in ids]}
        with patch.object(preflight.llm,'ask_json',side_effect=ask):
            result=preflight._reconceive(self.rows(29),'Costs kept rising.','local',1)
        self.assertEqual(len(result),29)
        self.assertEqual(sorted(len(ids) for ids,_ in calls),[5,12,12])
        self.assertTrue(all(kw['effort']=='low' and kw['max_tokens']==6000 for _,kw in calls))
    def test_missing_plan_stops_before_reusing_failed_original(self):
        with patch.object(preflight.llm,'ask_json',return_value={'shots':[]}):
            with self.assertRaises(RuntimeError):preflight._reconceive(self.rows(2),'Costs kept rising.','local',1)
