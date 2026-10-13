import unittest
from unittest.mock import Mock
from types import SimpleNamespace

import numpy as np
from dual_source import side_image, recognize_side, combine
from test_obs_tesseract import Engine


class Tests(unittest.TestCase):
    def test_native_colored_margin_does_not_hide_readable_105(self):
        import json,base64,cv2
        from pathlib import Path
        from source_selection import select_source
        f=json.loads(Path(__file__).with_name('sidebar_contour_cases.json').read_text())['readable_side_margin']
        crop=cv2.imdecode(np.frombuffer(base64.b64decode(f['image']),np.uint8),1)
        engine=Mock();engine.recognize.return_value=SimpleNamespace(txts=['105'])
        side=recognize_side(engine,crop,True,text_left=f['text_left'])
        self.assertEqual(side['current'],105)
        self.assertTrue(side['ignored_left_margin_overlay'])
        result=select_source({'value':{'current':108,'maximum':215}},side,
            {'top':{'available':True,'lower_percent':46.84,'upper_percent':49.34},
             'sidebar':{'available':True,'lower_percent':44.02,'upper_percent':51.63}},215)
        self.assertEqual(result['value']['current'],105)
        self.assertEqual(result['source'],'side_text')
        crop[:,8:11]=(180,0,180)
        engine.reset_mock()
        blocked=recognize_side(engine,crop,True,text_left=8)
        self.assertIsNone(blocked['current'])
        engine.recognize.assert_not_called()

    def test_neutral_margin_rim_is_trimmed(self):
        crop=np.zeros((15,54,3),dtype=np.uint8)
        crop[3:12,0:3]=230
        crop[3:12,7:10]=255
        crop[3:12,15:18]=255
        engine=Mock();engine.recognize.return_value=SimpleNamespace(txts=['65'])
        result=recognize_side(engine,crop,True,text_left=7)
        self.assertEqual(result['current'],65)
        self.assertTrue(result['ignored_neutral_margin_overlay'])
        self.assertEqual(result['visible_digit_groups'],2)

    def test_neutral_margin_rim_overlapping_text_is_rejected(self):
        crop=np.zeros((15,54,3),dtype=np.uint8)
        crop[3:12,0:10]=230
        engine=Mock()
        result=recognize_side(engine,crop,True,text_left=7)
        self.assertIsNone(result['current'])
        self.assertEqual(result['reason'],'neutral_margin_overlay_overlaps_text')
        engine.recognize.assert_not_called()

    def test_shortened_number_cannot_be_a_fallback(self):
        crop = np.zeros((15, 54, 3), dtype=np.uint8)
        for x in (4, 14, 24):
            crop[3:12, x:x+3] = 255
        engine = Mock()
        engine.recognize.return_value = SimpleNamespace(txts=['1'])
        result = recognize_side(engine, crop)
        self.assertEqual(result['visible_digit_groups'], 3)
        self.assertEqual(result['reason'], 'digit_count_mismatch')
        self.assertIsNone(result['current'])
        self.assertIsNone(combine({'raw':[''], 'value':None}, result, True)['value'])

    def test_digit_count_is_not_fixed_to_initial_maximum(self):
        crop = np.zeros((15, 54, 3), dtype=np.uint8)
        for x in (4, 14, 24, 34, 44):
            crop[3:12, x:x+3] = 255
        engine = Mock()
        engine.recognize.return_value = SimpleNamespace(txts=['10200'])
        self.assertEqual(recognize_side(engine, crop)['current'], 10200)

    def test_no_visible_text_is_white(self):
        for image in (np.zeros((0, 0, 3), dtype=np.uint8),
                      np.full((15, 54, 3), 40, dtype=np.uint8)):
            self.assertTrue(np.all(side_image(image) == 255))

    def test_side_mode_restored_when_recognition_fails(self):
        engine = Engine.__new__(Engine)
        from ocr_cache import PixelCache
        engine.cache=PixelCache()
        engine.tess = Mock()
        engine.tess.recognize.return_value = 1
        with self.assertRaises(RuntimeError):
            engine.recognize(np.zeros((20, 20), dtype=np.uint8), psm=8)
        self.assertEqual([call.args[1] for call in engine.tess.psm.call_args_list], [8, 7])
        engine.tess.clear.assert_called_once()
        engine.tess.clear_adaptive.assert_called_once()


if __name__ == '__main__':
    unittest.main()
