import unittest
from unittest.mock import Mock
import numpy as np
from text_occlusion import inspect_top_text
from test_obs_tesseract import recognize_top

class Tests(unittest.TestCase):
    def test_center_cursor_skips_engine_and_recovery(self):
        crop=np.full((14,770,3),(0,180,0),np.uint8)
        crop[:,380:393]=170
        engine=Mock()
        r=recognize_top(engine,np.zeros((30,30),np.uint8),True,raw_crop=crop)
        self.assertIsNone(r['value']);self.assertTrue(r['ocr_skipped'])
        engine.recognize.assert_not_called()
    def test_popup_and_offcenter_object(self):
        crop=np.full((14,770,3),(0,180,0),np.uint8)
        crop[:,360:650]=190
        self.assertTrue(inspect_top_text(crop)['occluded'])
        crop[:]=[0,180,0];crop[:,40:60]=190
        self.assertFalse(inspect_top_text(crop)['occluded'])
    def test_normal_short_white_glyphs_are_not_overlay(self):
        crop=np.full((14,770,3),(0,180,0),np.uint8)
        for x in range(360,408,8):crop[3:11,x:x+2]=255
        self.assertFalse(inspect_top_text(crop)['occluded'])

class MaximumTests(unittest.TestCase):
    def test_occluded_top_cannot_replace_cached_maximum(self):
        from source_selection import select_source
        from test_obs_pipeline import ConfirmMaximum
        from text_occlusion import unavailable
        guard=ConfirmMaximum(200)
        evidence={'sidebar':{'available':True,'lower_percent':94,'upper_percent':98},
                  'top':{'available':False,'reason':'neutral_overlay'}}
        r=select_source(unavailable({'occluded':True}),{'current':192},evidence,guard.maximum)
        self.assertEqual(r['value']['current'],192)
        self.assertIsNone(r['value']['maximum'])
        guard.update(r['value'])
        self.assertEqual(guard.maximum,200)
