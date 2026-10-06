import unittest
from unittest.mock import Mock

import numpy as np
from dual_source import side_image
from test_obs_tesseract import Engine


class Tests(unittest.TestCase):
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
