import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from orchestrator.stages import preflight as pf

class SourceCacheTests(unittest.TestCase):
    def setUp(self):
        from orchestrator import config as _cfg
        self._strict = _cfg.STRICT_GATES; _cfg.STRICT_GATES = True   # 07.10: строгий режим проверяется явно
        self.addCleanup(setattr, _cfg, 'STRICT_GATES', self._strict)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=Path(self.tmp.name)
        self.shots=[]
        for n in (1,2):
            name=f'{n}.png';(self.d/name).write_bytes(bytes([n])*3000)
            self.shots.append({'id':f's{n}','type':'broll','anchor':f'line {n}',
                'slots':[{'id':f's{n}_1','kind':'image','image':name,'caption':'Illustration',
                          'visual_intent':{'prompt':f'object {n}'}}]})
        for target,value in [('verify_web_photos',lambda *a:None),('is_blank',lambda *a:False),
                             ('_opening_ids',lambda *a:set()),('sheet',lambda *a,**k:b'sheet'),
                             ('frame_of',lambda slot,d:(d/slot['image']).read_bytes())]:
            p=patch.object(pf,target,value);p.start();self.addCleanup(p.stop)
        self.initial=patch.object(pf,'_initial_bad',return_value={}).start()
        self.addCleanup(patch.stopall)

    def run_check(self,vision):
        with patch.object(pf.llm,'ask_vision',side_effect=vision) as call:
            pf.check(self.d,self.shots,'line 1. line 2.','episode','image',passes=1)
            return call

    @staticmethod
    def good(prompt,*a,**kw):
        nums=[json.loads(line)['n'] for line in prompt.splitlines() if line.startswith('{"n":')]
        return {'checks':[{'n':n,'ok':True,'why':'Matching source'} for n in nums]}

    def test_changed_source_only_is_rechecked_and_manual_rejection_still_blocks(self):
        self.assertEqual(self.run_check(self.good).call_count,1)
        self.assertEqual(self.run_check(self.good).call_count,0)
        (self.d/'2.png').write_bytes(b'changed source'*300)
        call=self.run_check(self.good)
        self.assertEqual(call.call_count,1)
        prompt=call.call_args.args[0]
        self.assertIn('"n": 2',prompt);self.assertNotIn('"n": 1',prompt)
        self.initial.return_value={1:'Independent manual source rejection'}
        with patch.object(pf.llm,'ask_vision') as paid:
            with self.assertRaisesRegex(RuntimeError,'1 проблемных'):
                pf.check(self.d,self.shots,'line 1. line 2.','episode','image',passes=1)
            paid.assert_not_called()

    def test_incomplete_batch_never_grants_partial_cached_approval(self):
        with self.assertRaisesRegex(RuntimeError,'партия'):
            self.run_check(lambda *a,**k:{'checks':[{'n':1,'ok':True,'why':'Only one source'}]})
        self.assertFalse((self.d/'preflight_source_passes.json').exists())

    def test_changed_intent_requires_fresh_source_review(self):
        self.run_check(self.good)
        self.shots[0]['slots'][0]['visual_intent']['prompt']='a different named company'
        call=self.run_check(self.good)
        self.assertEqual(call.call_count,1)
        self.assertIn('"n": 1',call.call_args.args[0]);self.assertNotIn('"n": 2',call.call_args.args[0])

if __name__=='__main__':unittest.main()
