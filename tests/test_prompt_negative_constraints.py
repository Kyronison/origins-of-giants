import unittest
from orchestrator.stages.assets import _sanitize_prompt


class PromptNegativesTest(unittest.TestCase):
    def test_object_bans_preserve_the_requested_kitchen(self):
        prompt = '1948 kitchen, hands pressing patties, no documents, no screens, no faces'
        self.assertEqual(_sanitize_prompt(prompt), prompt)

    def test_document_replacement_retains_figure_bans(self):
        safe = _sanitize_prompt('1948 ledger on a desk, no people, no faces, no screens')
        self.assertIn('paper out of focus', safe)
        self.assertIn('no faces', safe)
        self.assertIn('no screens', safe)
        self.assertIn('no torsos', safe)

    def test_sign_precautions_keep_subject_and_existing_bans(self):
        safe = _sanitize_prompt('1948 delivery truck, hands unloading patties, no people, no documents')
        self.assertIn('delivery truck', safe)
        self.assertIn('no documents', safe)
        self.assertIn('no lettering', safe)

    def test_secondary_ledger_does_not_erase_the_calculator(self):
        safe = _sanitize_prompt('1980s mechanical desk calculator with blank display, beside a ledger, no people, no faces')
        self.assertIn('mechanical desk calculator', safe)
        self.assertNotIn('beside a ledger', safe)
        self.assertNotIn('extreme close-up of hands over a desk', safe)
        self.assertIn('no documents', safe)
        self.assertIn('no faces', safe)

    def test_secondary_blueprint_does_not_erase_aircraft_parts(self):
        safe = _sanitize_prompt('Wooden aircraft propeller, linen blueprint rolls, brass calipers, 1920s workshop, no people')
        self.assertIn('Wooden aircraft propeller', safe)
        self.assertIn('brass calipers', safe)
        self.assertNotIn('blueprint rolls', safe)
        self.assertIn('1920s workshop', safe)
        self.assertIn('no people', safe)
        self.assertIn('no readable text', safe)


if __name__ == '__main__': unittest.main()
