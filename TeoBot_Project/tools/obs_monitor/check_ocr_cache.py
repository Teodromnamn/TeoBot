import unittest
from types import SimpleNamespace
import numpy as np
from ocr_cache import PixelCache

class Tests(unittest.TestCase):
    def test_exact_pixels_mode_and_mutation(self):
        c=PixelCache();calls=[]
        def read(im,psm):
            calls.append(psm);return SimpleNamespace(txts=[str(im.sum())],scores=[.5])
        a=np.zeros((10,10),np.uint8)
        first=c.recognize(a,7,read);first.txts[0]='broken'
        self.assertEqual(c.recognize(a.copy(),7,read).txts,['0'])
        c.recognize(a,8,read);a[0,0]=1
        self.assertEqual(c.recognize(a,7,read).txts,['1'])
        self.assertEqual(len(calls),3)
    def test_limits_and_disable(self):
        read=lambda im,p:SimpleNamespace(txts=['1'],scores=[1.])
        c=PixelCache(limit=2,max_bytes=10)
        for n in range(10):c.recognize(np.full((2,2),n,np.uint8),7,read)
        self.assertLessEqual(len(c.entries),2);self.assertLessEqual(c.bytes,10)
        c=PixelCache(limit=0);a=np.zeros((2,2),np.uint8)
        c.recognize(a,7,read);c.recognize(a,7,read)
        self.assertEqual(c.hits,0);self.assertEqual(c.misses,2)
