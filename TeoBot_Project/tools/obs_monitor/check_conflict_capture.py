import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import cv2
import numpy as np
from conflict_capture import ConflictCapture
from test_obs_tesseract import binary


class Tests(unittest.TestCase):
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
