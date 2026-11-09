import unittest
from orchestrator.stages.preflight import _pairs


class NativeAssetPairsTests(unittest.TestCase):
    def test_text_quote_and_vector_map_have_no_optional_media(self):
        quote={'id':'q','type':'quote','slots':[],'data':{'text':'A sourced quotation'}}
        route={'id':'m','type':'map','slots':[],'data':{'points':[{'lat':42,'lon':-71}]}}
        self.assertEqual(_pairs([quote,route]),[])

    def test_insets_and_portraits_still_require_checking(self):
        inset={'id':'inset','image':'archive/wrong-city.jpg'}
        portrait={'id':'portrait','image':'archive/wrong-person.jpg'}
        route={'id':'m','type':'map','slots':[inset]}
        quote={'id':'q','type':'quote','slots':[portrait]}
        self.assertEqual(_pairs([route,quote]),[(route,inset),(quote,portrait)])

    def test_native_data_graphics_have_no_image_source_but_backdrops_do(self):
        graphics=[{'id':kind,'type':kind,'slots':[],'data':{'title':'Sourced values'}} for kind in ('chart','stat','compare')]
        self.assertEqual(_pairs(graphics),[])
        graphics[0]['image']='archive/background.jpg'
        self.assertEqual(_pairs(graphics),[(graphics[0],graphics[0])])

    def test_missing_broll_and_legacy_flat_quote_media_are_not_hidden(self):
        missing={'id':'b','type':'broll','slots':[]}
        flat={'id':'q','type':'quote','slots':[],'image':'archive/photo.jpg'}
        self.assertEqual(_pairs([missing,flat]),[(missing,missing),(flat,flat)])
