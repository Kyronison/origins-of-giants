import io,unittest
from PIL import Image
from orchestrator.stages.preflight import sheet

class SourceSheetTest(unittest.TestCase):
    def test_service_bands_do_not_cover_source_pixels(self):
        source=Image.new('RGB',(480,270),(40,80,160));b=io.BytesIO();source.save(b,'PNG')
        out=Image.open(io.BytesIO(sheet([(7,'Поздний снимок: Eddie Rickenbacker',b.getvalue())],cols=1))).convert('RGB')
        self.assertEqual(out.size,(492,322))
        for x,y in ((30,30),(250,25),(250,259)):
            actual=out.getpixel((6+x,6+20+y))
            self.assertTrue(all(abs(actual[k]-(40,80,160)[k])<8 for k in range(3)))
    def test_source_aspect_is_preserved(self):
        source=Image.new('RGB',(240,270),(40,80,160));b=io.BytesIO();source.save(b,'PNG')
        out=Image.open(io.BytesIO(sheet([(1,'Portrait',b.getvalue())],cols=1))).convert('RGB')
        self.assertLess(out.getpixel((20,150))[0],30)
        self.assertGreater(out.getpixel((246,150))[2],140)
