import unittest
from unittest.mock import Mock,patch
import numpy as np
from hybrid_counter import HybridCounter

class Tests(unittest.TestCase):
    def setUp(self):
        self.templates=Mock();self.engine=Mock();self.reader=HybridCounter(self.templates,self.engine);self.crop=np.zeros((11,43,3),np.uint8)
        self.guard=patch('hybrid_counter.valid_crop',return_value=True);self.guard.start();self.addCleanup(self.guard.stop)
    def test_template_success_does_not_run_ocr(self):
        self.templates.read.return_value={'current':111,'reason':None}
        with patch('hybrid_counter.recognize_top') as ocr:
            result=self.reader.read(self.crop,'top','hp')
        self.assertEqual(result['current'],111);self.assertEqual(result['method'],'native_template');ocr.assert_not_called()
    def test_zero_is_success_not_fallback(self):
        self.templates.read.return_value={'current':0,'reason':None}
        self.assertEqual(self.reader.read(self.crop,'side','mp')['current'],0)
        self.engine.recognize.assert_not_called();self.assertEqual(self.reader.counts['fallback_attempts'],0)
    def test_top_rejection_falls_back(self):
        self.templates.read.return_value={'current':None,'reason':'glyph_not_distinct'}
        with patch('hybrid_counter.recognize_top',return_value={'value':{'current':101,'maximum':215}}):
            result=self.reader.read(self.crop,'top','hp')
        self.assertEqual(result['current'],101);self.assertEqual(result['method'],'tesseract_fallback');self.assertEqual(self.reader.counts['fallback_numeric_results'],1)
    def test_side_rejection_falls_back(self):
        self.templates.read.return_value={'current':None,'reason':'invalid_glyph_count'}
        with patch('hybrid_counter.recognize_side',return_value={'current':111}):
            self.assertEqual(self.reader.read(self.crop,'side','hp')['current'],111)
    def test_failed_fallback_remains_unavailable(self):
        self.templates.read.return_value={'current':None,'reason':'glyph_not_distinct'}
        with patch('hybrid_counter.recognize_side',return_value={'current':None}):
            self.assertIsNone(self.reader.read(self.crop,'side','hp')['current'])
    def test_occlusion_blocks_both_methods(self):
        with patch('hybrid_counter.valid_crop',return_value=False):result=self.reader.read(self.crop,'side','mp')
        self.assertIsNone(result['current']);self.templates.read.assert_not_called();self.engine.recognize.assert_not_called()
if __name__=='__main__':unittest.main()
