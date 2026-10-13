import unittest
import numpy as np
from template_counter import TemplateCounter,normalize

class Tests(unittest.TestCase):
    def model(self,ambiguous=False):
        one=np.full((8,3),0,np.uint8)
        other=np.full((8,6),255,np.uint8);other[0,:]=0;other[:,5]=0;other[-1,:]=0
        return {'templates':{'side':{d:[{'mask':normalize(g).tolist(),'aspect':g.shape[1]/g.shape[0]}] for d,g in [('1',one),('7',one if ambiguous else other)]}}}
    def crop(self):
        image=np.full((11,30,3),50,np.uint8)
        for x in (3,10,17):image[2:10,x:x+3]=255
        return image
    def test_repeated_ones_without_ocr(self):
        self.assertEqual(TemplateCounter(self.model()).read(self.crop(),'side')['current'],111)
    def test_blank_unavailable(self):
        self.assertIsNone(TemplateCounter(self.model()).read(np.zeros((11,30,3),np.uint8),'side')['current'])
    def test_indistinguishable_templates_rejected(self):
        self.assertIsNone(TemplateCounter(self.model(True)).read(self.crop(),'side')['current'])
    def test_unknown_solid_wide_shape_rejected(self):
        image=np.zeros((11,30,3),np.uint8);image[2:10,3:11]=255
        self.assertIsNone(TemplateCounter(self.model()).read(image,'side')['current'])
    def test_strict_error_limit_rejects_damaged_digit(self):
        image=self.crop();image[4:6,3:5]=50
        self.assertIsNone(TemplateCounter(self.model(),max_error=.001).read(image,'side')['current'])
if __name__=='__main__':unittest.main()
