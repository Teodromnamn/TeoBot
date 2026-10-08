import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import cv2
import numpy as np
from conflict_capture import ConflictCapture, diagnostic_needed
from test_obs_tesseract import binary


class Tests(unittest.TestCase):
    def test_rejected_side_reading_remains_diagnostic(self):
        self.assertTrue(diagnostic_needed({'verification':'side_unreadable',
                                          'side':{'reason':'digit_count_mismatch'}}))
        self.assertFalse(diagnostic_needed({'verification':'side_unreadable',
                                           'side':{'reason':'unreadable'}}))

    def test_missing_value_captured_but_normal_confirmation_wait_excluded(self):
        self.assertTrue(diagnostic_needed({'value':None, 'confirmation':'sources_not_agreed'}))
        self.assertFalse(diagnostic_needed({'value':None, 'confirmation':'waiting_second_frame'}))
        self.assertTrue(diagnostic_needed({'value':None, 'side':None}))

    def test_side_fill_crop_saved_from_same_frame(self):
        frame = np.full((30,60,3),170,dtype=np.uint8)
        frame[15:20,30:40] = (255,0,0)
        boxes = [(0,0,20,10),(0,10,20,10)]
        bars = [(30,15,10,5),(30,15,10,5)]
        analysis = {'readings':[{'value':None,'side':None},{'value':None,'side':None}]}
        with tempfile.TemporaryDirectory() as folder:
            recorder = ConflictCapture(Path(folder)/'cases')
            self.assertTrue(recorder.capture(frame,analysis,boxes,boxes,binary,bars))
            image = cv2.imread(str(Path(folder)/'cases/case_000/mp_side_bar.png'))
            np.testing.assert_array_equal(image,frame[15:20,30:40])
            meta = json.loads((Path(folder)/'cases/case_000/reading.json').read_text())
            self.assertEqual(meta['side_bar_rectangles'], [list(b) for b in bars])

    def test_limits_same_frame_crops_and_archive(self):
        now=[0.]
        frame=np.full((50,80,3),170,dtype=np.uint8)
        frame[20:30]=210
        boxes=[(0,0,30,10),(0,20,30,10)]
        readings=[{'raw':['155/185'],'verification':'conflict',
                   'side':{'raw':'15','current':15},'value':None},
                  {'raw':['90/90'],'verification':'current_agrees',
                   'side':{'raw':'90','current':90},'value':{'current':90}}]
        with tempfile.TemporaryDirectory() as folder:
            recorder=ConflictCapture(Path(folder)/'cases',limit=2,clock=lambda:now[0])
            self.assertTrue(recorder.capture(frame,{'readings':readings},boxes,boxes,binary))
            now[0]=1
            self.assertFalse(recorder.capture(frame,{'readings':readings},boxes,boxes,binary))
            now[0]=5
            self.assertTrue(recorder.capture(frame,{'readings':readings},boxes,boxes,binary))
            now[0]=11
            self.assertFalse(recorder.capture(frame,{'readings':readings},boxes,boxes,binary))
            path=recorder.finish()
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(len(archive.namelist()),22)
                meta=json.loads(archive.read('case_000/reading.json'))
                self.assertEqual(meta['analysis']['readings'],readings)
                crop=cv2.imdecode(np.frombuffer(archive.read('case_000/mp_side_original.png'),dtype=np.uint8),1)
                np.testing.assert_array_equal(crop,frame[20:30,:30])

    def test_no_capture_when_sources_agree(self):
        recorder=ConflictCapture('must_not_be_created')
        self.assertFalse(recorder.capture(None,{'readings':[{'verification':'current_agrees'}]},None,None,None))
        self.assertEqual(recorder.count,0)

    def test_write_failure_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'blocked'
            path.write_text('not a directory')
            recorder=ConflictCapture(path)
            self.assertFalse(recorder.capture(None,{'readings':[{'verification':'conflict','side':{}}]},[],[],None))
            self.assertIsNotNone(recorder.error)


if __name__=='__main__':
    unittest.main()
