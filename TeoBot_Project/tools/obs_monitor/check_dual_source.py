"""Deterministic verification/scheduling tests; no camera or OCR models."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from dual_source import DualAnalyzer, combine
from test_obs_pipeline import ConfirmMaximum, publish, result_status


def top(current=50, maximum=100):
    return {'raw':[f'{current}/{maximum}'], 'value':None if current is None else
            {'current':current, 'maximum':maximum, 'percent':100*current/maximum}}


class Tests(unittest.TestCase):
    def test_agreement_is_current_only(self):
        r = combine(top(), {'current':50}, True)
        self.assertEqual(r['verification'], 'current_agrees')
        self.assertEqual(combine(top(), None, False)['verification'], 'not_checked')

    def test_conflict_keeps_evidence_not_value(self):
        r = combine(top(), {'current':65}, True)
        self.assertIsNone(r['value'])
        self.assertEqual(r['top_value']['current'],50)
        self.assertEqual(r['side']['current'],65)

    def test_fallback_does_not_invent_maximum(self):
        r = combine(top(None), {'current':37}, True,180)
        self.assertEqual(r['value']['current'],37)
        self.assertIsNone(r['value']['maximum'])
        self.assertIsNone(r['value']['percent'])
        self.assertAlmostEqual(r['value']['estimated_percent'],100*37/180)
        self.assertEqual(ConfirmMaximum(180).update(r['value']), 'side_only')

    def test_growth_beyond_cached_max(self):
        r = combine(top(None), {'current':10200}, True,60)
        self.assertEqual(r['value']['current'],10200)
        self.assertIsNone(r['value']['estimated_percent'])
        guard=ConfirmMaximum(60)
        self.assertEqual(guard.update(top(10200,10200)['value']), 'maximum_pending')
        self.assertEqual(guard.update(top(10200,10200)['value']), 'maximum_changed')

    def test_publication_independent_and_expires(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'latest.json'
            readings=[combine(top(),{'current':65},True), combine(top(),{'current':50},True)]
            publish(path,'KONFLIKT_ZRODEL',readings,100,250,['source_conflict','ok'])
            data=json.loads(path.read_text())
            self.assertIsNone(data['hp'])
            self.assertTrue(data['resources']['mp']['verified_current'])
            publish(path,'WYNIK_ZBYT_STARY',readings,300,250,['source_conflict','ok'])
            data=json.loads(path.read_text())
            self.assertIsNone(data['mp'])
            self.assertFalse(data['resources']['mp']['verified_current'])
        self.assertEqual(result_status('OK',50,20,['source_conflict','ok']), 'KONFLIKT_ZRODEL')

    def test_schedule_same_frame_and_no_cached_confirmation(self):
        now=[0.]
        frames=[]
        class Top:
            engine=None
            readings=[top(),top()]
            def analyze(self, frame):
                frames.append(frame)
                return dict(readings=self.readings,prepare_ms=0,recognition_ms=0,crop_sizes=[])
        model=Top()
        dual=DualAnalyzer(model,clock=lambda:now[0])
        dual.boxes=[(0,0,1,1)]*2
        dual.guards=[ConfirmMaximum(100)]*2
        dual.geometry_ok=lambda f:True
        calls=[]
        side_value=[50]
        def read(frame,index):
            self.assertIs(frame,frames[-1])
            calls.append(index)
            return {'current':side_value[0]}
        dual.read_side=read
        frame=np.zeros((2,2,3),dtype=np.uint8)
        self.assertTrue(dual.analyze(frame)['side_checked'])
        now[0]=.1
        r=dual.analyze(frame)
        self.assertFalse(r['side_checked'])
        self.assertEqual(r['readings'][0]['verification'],'not_checked')
        now[0]=.5
        side_value[0]=65
        self.assertEqual(dual.analyze(frame)['readings'][0]['verification'],'conflict')
        now[0]=.51
        self.assertTrue(dual.analyze(frame)['side_checked'])
        side_value[0]=50
        now[0]=.6
        dual.analyze(frame)
        self.assertFalse(dual.conflict_pending)
        self.assertEqual(len(calls),8)

    def test_missing_top_triggers_immediately(self):
        class Top:
            engine=None
            def analyze(self, frame):
                return dict(readings=[top(None),top()],prepare_ms=0,recognition_ms=0,crop_sizes=[])
        dual=DualAnalyzer(Top(),clock=lambda:0.)
        dual.boxes=[(0,0,1,1)]*2
        dual.next_check=10
        dual.guards=[ConfirmMaximum(100)]*2
        dual.geometry_ok=lambda f:True
        dual.read_side=lambda f,i:{'current':50}
        self.assertTrue(dual.analyze(None)['side_checked'])


if __name__=='__main__':
    unittest.main()
