import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from orchestrator.stages import assets

class ImagePurchasePlanTests(unittest.TestCase):
    def test_document_plan_stops_before_any_paid_request(self):
        with tempfile.TemporaryDirectory() as tmp,patch('fal_client.subscribe') as buy:
            with self.assertRaisesRegex(ValueError,'purchase blocked'):
                assets._image('1980s ledger on desk, no people',Path(tmp),'s','model')
            buy.assert_not_called()

    def test_secondary_document_is_not_silently_removed(self):
        with self.assertRaisesRegex(ValueError,'new explicit visual plan'):
            assets.validate_image_prompt('Aircraft engine, technical blueprint beside it, no people')

    def test_contradictory_figures_stop_before_purchase(self):
        with tempfile.TemporaryDirectory() as tmp,patch('fal_client.subscribe') as buy:
            with self.assertRaisesRegex(ValueError,'at the same time'):
                assets._image('Two workers in a hangar, no people, no figures',Path(tmp),'s','model')
            buy.assert_not_called()

    def test_negative_bans_are_not_positive_requests(self):
        assets.validate_image_prompt('Close-up of a propeller hub, 1930s, no documents, no people, no figures')
        assets.validate_image_prompt('Hands tightening a bolt, no people, no faces')

    def test_object_only_style_does_not_add_direction_for_faces(self):
        with tempfile.TemporaryDirectory() as tmp,patch('fal_client.subscribe',return_value={'images':[{'url':'cached'}]}) as buy,patch.object(assets,'_get',return_value=b'image'):
            assets._image('Close-up of a wrench, no people',Path(tmp),'s','fal-ai/test')
            prompt=buy.call_args.kwargs['arguments']['prompt']
            self.assertNotIn('looking at camera',prompt)
            self.assertIn('Close-up of a wrench',prompt)

if __name__=='__main__':unittest.main()
