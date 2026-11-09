import unittest
from orchestrator import llm,visual_integrity

class VisionArrayTest(unittest.TestCase):
    def test_all_verdicts_and_rejection_are_preserved(self):
        result=llm.extract_vision_json('```json\n[{"n":1,"ok":true,"why":"right source"},{"n":2,"ok":false,"why":"wrong company"}]\n```')
        verdicts=visual_integrity.verdicts(result,{1,2})
        self.assertIs(verdicts[2]['ok'],False)
        self.assertEqual(len(verdicts),2)

    def test_missing_duplicate_and_string_boolean_cannot_pass(self):
        for text in ('[{"n":1,"ok":true,"why":"ok"}]',
                     '[{"n":1,"ok":true,"why":"ok"},{"n":1,"ok":true,"why":"ok"}]',
                     '[{"n":1,"ok":"true","why":"ok"}]'):
            with self.assertRaises(ValueError):
                visual_integrity.verdicts(llm.extract_vision_json(text),{1,2})

if __name__=='__main__':unittest.main()
