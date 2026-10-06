import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import cv2
import numpy as np
from dataset_capture import DatasetCapture
from dual_source import ConfirmationGate


class Tests(unittest.TestCase):
    def test_sampling_limit_raw_identity_and_empty_labels(self):
        now = [0.]
        frame = np.arange(40*80*3, dtype=np.uint8).reshape(40,80,3)
        boxes = [(0,0,30,10),(10,20,30,10)]
        with tempfile.TemporaryDirectory() as folder:
            recorder = DatasetCapture(Path(folder)/'samples',limit=2,clock=lambda:now[0])
            recorder.calibrate(frame,boxes,boxes)
            self.assertTrue(recorder.capture(frame, {}, boxes, boxes, boxes))
            now[0] = .1
            self.assertFalse(recorder.capture(frame, {}, boxes, boxes, boxes))
            now[0] = .3
            self.assertTrue(recorder.capture(frame, {}, boxes, boxes, boxes))
            now[0] = 1.
            self.assertFalse(recorder.capture(frame, {}, boxes, boxes, boxes))
            with zipfile.ZipFile(recorder.finish()) as archive:
                self.assertEqual(len(archive.namelist()),21)
                self.assertIn('calibration/mp_side_bar.png',archive.namelist())
                image = cv2.imdecode(np.frombuffer(archive.read('case_00000/mp_side_bar.png'),np.uint8),1)
                np.testing.assert_array_equal(image,frame[20:30,10:40])
                labels = list(csv.DictReader(io.StringIO(archive.read('labels.csv').decode())))
                self.assertEqual(len(labels),2)
                self.assertEqual(labels[0]['hp_current'],'')
                meta = json.loads(archive.read('case_00001/reading.json'))
                self.assertAlmostEqual(meta['elapsed_s'],.3)

    def test_strict_requires_two_fresh_complete_agreements(self):
        gate = ConfirmationGate()
        reading = {'value':{'current':111,'maximum':185}, 'verification':'current_agrees'}
        self.assertIsNone(gate.apply(reading,1.)['value'])
        self.assertEqual(gate.apply(reading,1.1)['value']['current'],111)
        self.assertIsNone(gate.apply(reading,1.5)['value'])
        bad = dict(reading,verification='top_unreadable')
        self.assertIsNone(gate.apply(bad,1.6)['value'])
        self.assertIsNone(gate.apply(reading,1.7)['value'])
        self.assertIsNone(gate.apply(reading,1.7)['value'])
        changed = dict(reading,value={'current':110,'maximum':185})
        self.assertIsNone(gate.apply(changed,1.8)['value'])
        self.assertEqual(gate.apply(changed,1.9)['confirmation'],'two_frames_agree')


if __name__ == '__main__':
    unittest.main()
