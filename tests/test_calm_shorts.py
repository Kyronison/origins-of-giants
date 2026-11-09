"""Content contracts for the new Shorts profile, independent of paid services."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from orchestrator.stages import shorts

class CalmShortsTests(unittest.TestCase):
    def test_complete_phrases_preserve_every_spoken_word(self):
        text='A family restaurant keeps control over every store.'
        words=[{'w':w,'s':i*.35,'e':i*.35+.25} for i,w in enumerate(text.split())]
        with patch.object(shorts.config,'SHORT_STYLE','calm-story-v1'):
            caps=shorts._captions(words,set(),4)
        self.assertEqual([w['w'] for c in caps for w in c['words']],text.split())
        self.assertEqual(len(caps),2)
        self.assertTrue(all(c['start']<c['end'] for c in caps))

    def test_slow_scene_plan_is_accepted_instead_of_retrying_for_ten_cuts(self):
        plan={'script':'Family owns the restaurants. Fresh food limits expansion. Trucks connect the stores.','cta':''}
        scenes=[{'anchor':'Family owns'},{'anchor':'Fresh food'},{'anchor':'Trucks connect'}]
        with patch.object(shorts.config,'SHORT_STYLE','calm-story-v1'),patch.object(shorts.llm,'ask_json',return_value={'shots':scenes}) as ask:
            self.assertEqual(shorts._shots('sample',plan,{},{}),scenes)
        self.assertEqual(ask.call_count,1)

    def test_wrong_narration_anchors_stop_the_new_plan(self):
        scenes=[{'anchor':'different person'},{'anchor':'wrong company'},{'anchor':'invented date'}]
        with patch.object(shorts.config,'SHORT_STYLE','calm-story-v1'),patch.object(shorts.llm,'ask_json',return_value={'shots':scenes}):
            with self.assertRaises(ValueError):shorts._shots('sample',{'script':'The family keeps every restaurant.','cta':''},{},{})

    def test_legacy_caption_profile_still_has_three_word_groups(self):
        words=[{'w':w,'s':i*.35,'e':i*.35+.25} for i,w in enumerate('The family owns every restaurant in the chain.'.split())]
        with patch.object(shorts.config,'SHORT_STYLE','legacy'):
            caps=shorts._captions(words,set(),4)
        self.assertEqual([len(c['words']) for c in caps],[3,3,2])

    def test_a_single_bad_scene_cannot_be_silently_dropped(self):
        scenes=[{'anchor':'Family owns'},{'anchor':'Fresh food'},{'anchor':'Trucks connect'},{'anchor':'Fake event'}]
        with patch.object(shorts.config,'SHORT_STYLE','calm-story-v1'),patch.object(shorts.llm,'ask_json',return_value={'shots':scenes}):
            with self.assertRaises(ValueError):shorts._shots('sample',{'script':'Family owns the restaurants. Fresh food limits expansion. Trucks connect the stores.','cta':''},{},{})

    def test_repeating_the_same_anchor_does_not_force_three_cuts(self):
        scenes=[{'anchor':'Family owns'} for _ in range(3)]
        with patch.object(shorts.config,'SHORT_STYLE','calm-story-v1'),patch.object(shorts.llm,'ask_json',return_value={'shots':scenes}):
            with self.assertRaises(ValueError):shorts._shots('sample',{'script':'Family owns the restaurants.','cta':''},{},{})

    def test_motion_steps_must_be_grounded_in_narration(self):
        panel={'panel':{'layout':'flow','headline':'Fresh food limits expansion',
                        'nodes':['Trucks connect stores','Fresh food limits expansion']}}
        text='Fresh food limits expansion. Trucks connect stores.'
        self.assertEqual(shorts._calm_panel(panel,text)['layout'],'flow')
        panel['panel']['nodes'][0]='Franchise fees pay investors'
        with self.assertRaises(ValueError):shorts._calm_panel(panel,text)

    def test_number_cannot_be_repeated_as_motion_step(self):
        panel={'panel':{'layout':'flow','headline':'The family keeps control',
                        'nodes':['The family keeps control','Sales reach 6 million']}}
        with self.assertRaises(ValueError):shorts._calm_panel(panel,'The family keeps control. Sales reach 6 million.')

    def test_motion_adapter_preserves_video_source_and_stops_before_end_card(self):
        cut=[{'start':0,'end':8,'src':'clip.mp4','credit':'Archive'},
             {'start':8,'end':16,'panel':{'layout':'flow','nodes':['One','Two'],'headline':'Mechanism'}}]
        panels=shorts._calm_panels(cut,14)
        self.assertEqual(panels[0]['src'],'clip.mp4')
        self.assertEqual(panels[-1]['end'],14)

    def test_plain_v4_voice_is_reused_and_charged_to_parent(self):
        words=[{'w':'Family','s':0,'e':.4},{'w':'owns.','s':.5,'e':1.0}]
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{'ELEVENLABS_VOICE_ID':'test-voice'}), \
             patch.object(shorts.A,'_tts_fal_v4',return_value=(b'audio',None)) as tts, \
             patch.object(shorts.A,'_words',return_value=words), patch.object(shorts.A,'_loudnorm'), \
             patch.object(shorts.A,'_duration',return_value=1.1):
            original=shorts.A.TTS_CTX.get('vid','')
            tts.side_effect=lambda *args:(self.assertEqual(shorts.A.TTS_CTX['vid'],'parent') or b'audio',None)
            shorts._calm_voice('Family owns.',Path(tmp),'parent')
            shorts._calm_voice('Family owns.',Path(tmp),'parent')
            self.assertEqual(tts.call_count,1)
            self.assertEqual(shorts.A.TTS_CTX['vid'],original)
            self.assertEqual((Path(tmp)/'voice.mp3').read_bytes(),b'audio')

    def test_missing_spoken_word_cannot_be_cached_as_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{'ELEVENLABS_VOICE_ID':'test-voice'}), \
             patch.object(shorts.A,'_tts_fal_v4',return_value=(b'audio',None)), \
             patch.object(shorts.A,'_words',return_value=[{'w':'Family','s':0,'e':.4}]):
            with self.assertRaises(ValueError):shorts._calm_voice('Family owns.',Path(tmp),'parent')
            self.assertFalse((Path(tmp)/'voice.sha').exists())

if __name__=='__main__':unittest.main()
