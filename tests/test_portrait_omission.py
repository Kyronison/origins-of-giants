import unittest
from orchestrator.stages.story_assets import fill_missing_portraits


class PortraitOmissionTests(unittest.TestCase):
    def test_editorial_omission_survives_portrait_reuse(self):
        source = {'role': 'portrait', 'person': 'Esther Snyder', 'image': 'source.jpg'}
        omitted = {'role': 'portrait', 'person': 'Esther Snyder', 'image': None,
                   'portrait_omitted': True}
        missing = {'role': 'portrait', 'person': 'Esther Snyder', 'image': None}
        scenes = [{'id': 'source', 'type': 'people', 'slots': [source]},
                  {'id': 'text_quote', 'type': 'quote', 'slots': [omitted]},
                  {'id': 'ordinary_missing', 'type': 'quote', 'slots': [missing]}]
        self.assertEqual(fill_missing_portraits(scenes), 1)
        self.assertIsNone(omitted['image'])
        self.assertEqual(missing['image'], 'source.jpg')


if __name__ == '__main__':
    unittest.main()
