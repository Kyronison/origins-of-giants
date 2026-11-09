import copy
import json
import unittest
from orchestrator import visual_integrity as vi


class VisualSlotContextTests(unittest.TestCase):
    def test_portrait_and_activity_have_separate_requirements(self):
        portrait = {'id': 'portrait', 'role': 'portrait', 'person': 'Lynsi Snyder'}
        activity = {'id': 'activity', 'role': 'activity', 'person': 'Lynsi Snyder'}
        scene = {'id': 'people', 'slots': [portrait, activity],
                 'data': {'persons': [{'name': 'Lynsi Snyder', 'portrait': 0, 'activity': 1}]}}
        first = json.loads(vi.context(1, scene, portrait, 'She discusses the commissary.'))
        second = json.loads(vi.context(2, scene, copy.deepcopy(activity), 'She discusses the commissary.'))
        self.assertEqual(first['slot']['index'], 0)
        self.assertEqual(first['slot']['role'], 'portrait')
        self.assertEqual(second['slot']['index'], 1)
        self.assertEqual(second['slot']['role'], 'activity')
        self.assertEqual(second['scene_data'], scene['data'])

    def test_role_does_not_hide_conflicting_source_or_original_intent(self):
        slot = {'id': 'report', 'role': 'main',
                'archive': {'description': 'U.S. Steel annual report'},
                'visual_intent': {'caption': 'Greyhound financial results'}}
        evidence = json.loads(vi.context(1, {'id': 'scene'}, slot, 'Greyhound revenue.'))
        self.assertEqual(evidence['source']['description'], 'U.S. Steel annual report')
        self.assertEqual(evidence['original_intent']['caption'], 'Greyhound financial results')
        self.assertEqual(evidence['narration'], 'Greyhound revenue.')

    def test_map_context_keeps_coordinates_and_source_but_does_not_send_polygon_vertices(self):
        scene={'id':'route','type':'map','data':{'title':'Shuttle','points':[{'name':'Boston','lat':42.36,'lon':-71.06}],
                  'route':[0,1],'land':{'coordinates':[[[1,2],[3,4]]]}}}
        slot={'id':'inset','archive':{'description':'Wrong city photograph'},'visual_intent':{'query':'Boston, 1961'}}
        before=copy.deepcopy(scene)
        evidence=json.loads(vi.context(1,scene,slot,'The shuttle served Boston.'))
        self.assertEqual(evidence['scene_data']['points'],scene['data']['points'])
        self.assertEqual(evidence['scene_data']['route'],[0,1])
        self.assertEqual(evidence['source'],slot['archive'])
        self.assertEqual(evidence['original_intent'],slot['visual_intent'])
        self.assertNotIn('coordinates',evidence['scene_data']['land'])
        self.assertEqual(scene,before)
        old_hash=evidence['scene_data']['land']['geometry_sha256']
        scene['data']['land']['coordinates'][0][0][0]=99
        self.assertNotEqual(old_hash,vi.scene_context_data(scene)['land']['geometry_sha256'])


if __name__ == '__main__':
    unittest.main()
