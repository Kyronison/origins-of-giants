import unittest
from orchestrator.stages.preflight import _intent_words


class IntentWordsTests(unittest.TestCase):
    def test_safety_exclusions_do_not_define_visual_similarity(self):
        shared = ', no people anywhere, no heads or torsos or silhouettes, no text or logos or numbers'
        first = _intent_words('restaurant serving hatch with parked sedans' + shared)
        second = _intent_words('metal intercom speaker with perforated grille' + shared)
        self.assertLess(len(first & second) / len(first | second), 0.6)
        self.assertNotIn('silhouettes', first)

    def test_matching_subject_survives_different_exclusions(self):
        first = _intent_words('metal intercom speaker with perforated grille, no figures')
        second = _intent_words('metal intercom speaker with perforated grille, without lettering')
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
