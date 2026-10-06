import unittest
from unittest.mock import Mock
from types import SimpleNamespace

import numpy as np
from dual_source import side_image, recognize_side, combine
from test_obs_tesseract import Engine


class Tests(unittest.TestCase):
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
        engine.tess = Mock()
        engine.tess.recognize.return_value = 1
        with self.assertRaises(RuntimeError):
            engine.recognize(np.zeros((20, 20), dtype=np.uint8), psm=8)
        self.assertEqual([call.args[1] for call in engine.tess.psm.call_args_list], [8, 7])
        engine.tess.clear.assert_called_once()
        engine.tess.clear_adaptive.assert_called_once()


if __name__ == '__main__':
    unittest.main()
