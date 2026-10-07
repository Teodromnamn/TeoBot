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

class ColoredTests(unittest.TestCase):
    def test_brown_object_crossing_maximum_blocks_ocr(self):
        crop=np.full((14,770,3),(0,210,0),np.uint8)
        crop[3:11,403:410]=[45,110,175]
        r=inspect_top_text(crop)
        self.assertTrue(r['occluded'])
        self.assertEqual(r['reason'],'foreign_colored_object')
        engine=Mock();result=recognize_top(engine,np.zeros((10,10),np.uint8),True,raw_crop=crop)
        engine.recognize.assert_not_called()
        self.assertIsNone(result['value'])
    def test_filled_empty_background_and_white_antialias_allowed(self):
        crop=np.full((14,770,3),30,np.uint8);crop[:,:390]=[0,210,0]
        crop[3:11,370:373]=[100,230,100]
        self.assertFalse(inspect_top_text(crop)['occluded'])
    def test_colored_mp_suffix_does_not_block_main_ratio(self):
        crop=np.full((14,770,3),(180,60,0),np.uint8)
        crop[3:11,422:430]=[0,180,220]
        self.assertFalse(inspect_top_text(crop)['occluded'])

    def test_wide_mp_single_digit_ratio_suffix_is_not_overlay(self):
        crop=np.full((14,858,3),(180,60,0),np.uint8)
        crop[4:10,458:464]=[0,180,220]
        self.assertFalse(inspect_top_text(crop,'mp')['occluded'])

    def test_thin_flat_gray_fragment_crossing_text_is_occluded(self):
        crop=np.full((14,858,3),(0,180,0),np.uint8)
        crop[3:11,414:417]=220
        r=inspect_top_text(crop,'hp')
        self.assertTrue(r['occluded'])
        self.assertEqual(r['reason'],'flat_gray_text_overlay')
