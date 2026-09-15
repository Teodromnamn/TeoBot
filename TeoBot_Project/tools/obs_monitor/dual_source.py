"""Same-frame text verification. Never propagate verification across frames."""
import re
import time

import cv2
import numpy as np
from test_side_counters import locate


def side_image(crop):
    gray = crop.min(axis=2)
    large = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    binary = np.where(large > 100, 0, 255).astype('uint8')
    return cv2.copyMakeBorder(binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)


def combine(top, side, checked, cached_maximum=None):
    """side is this frame's reading or None. A cached maximum is never exact."""
    result = dict(top)
    result.update(source='top_text', verification='not_checked', side=side,
                  quality='exact' if top['value'] else 'unavailable')
    if not checked:
        return result
    tv = top['value']
    current = side.get('current') if side else None
    if tv is not None and current is not None:
        if tv['current'] == current:
            result.update(source='top_and_side_text', verification='current_agrees')
        else:
            result.update(value=None, source=None, quality='unavailable',
                          verification='conflict', top_value=tv)
    elif tv is not None:
        result['verification'] = 'side_unreadable'
    elif current is not None:
        # Do not reject a possible level-up merely because cached max is lower.
        percent = (100*current/cached_maximum if cached_maximum
                   and current <= cached_maximum else None)
        result.update(source='side_text', verification='top_unreadable', quality='current_only',
                      value={'current': current, 'maximum': None, 'percent': None,
                             'last_confirmed_maximum': cached_maximum,
                             'estimated_percent': percent, 'maximum_source': 'cached_top_text'})
    else:
        result.update(source=None, verification='both_unreadable')
    return result


class DualAnalyzer:
    def __init__(self, top_analyzer, clock=time.perf_counter):
        self.top = top_analyzer
        self.engine = top_analyzer.engine
        self.clock = clock
        self.boxes = None
        self.next_check = 0.
        self.fast_until = 0.
        self.conflict_pending = False

    def read_side(self, frame, index):
        x,y,w,h = self.boxes[index]
        image = side_image(frame[y:y+h, x:x+w])
        result = self.engine.recognize(image)
        raw = result.txts[0].strip()
        return {'raw': raw, 'current': int(raw) if re.fullmatch(r'[0-9]+', raw) else None}

    def calibrate(self, frame, readings, guards):
        self.boxes, bars = locate(frame, return_bars=True)
        self.shape = frame.shape
        self.guards = guards
        red, blue = bars
        step = blue[1]-red[1]
        x0 = max(0, red[0]-round(step*1.8))
        x1 = red[0]-2
        y0 = max(0, red[1]-2)
        y1 = blue[1]+blue[3]+2
        self.anchor_box = (x0,y0,x1,y1)
        self.anchor = frame[y0:y1,x0:x1].copy()
        if self.anchor.size == 0:
            raise RuntimeError('Brak kotwicy bocznych paskow')
        side = [self.read_side(frame,i) for i in range(2)]
        if any(readings[i]['value'] is None or side[i]['current'] != readings[i]['value']['current']
               for i in range(2)):
            raise RuntimeError(f'Kalibracja bocznych liczb niezgodna z gora: {side}. '
                               'Pokaz pelne HP/MP bez popupow i uruchom ponownie.')
        print(f'Boczne HP/MP: {self.boxes}; zgodne z gora. Weryfikacja 2/s.', flush=True)
        return {'side_rectangles': self.boxes, 'side_readings': side}

    def geometry_ok(self, frame):
        if frame.shape != self.shape:
            return False
        x0,y0,x1,y1 = self.anchor_box
        patch = frame[y0:y1,x0:x1]
        return float(np.mean(np.abs(patch.astype(float)-self.anchor))) < 25

    def analyze(self, frame):
        started = self.clock()
        analysis = self.top.analyze(frame)
        readings = analysis['readings']
        if self.boxes is None:
            raise RuntimeError('Boczny odczyt wymaga kalibracji')
        # Errors trigger immediate verification, not a delayed half-second check.
        due = self.conflict_pending or started >= self.next_check or any(r['value'] is None for r in readings)
        side_ms = 0.
        if due:
            begin = self.clock()
            side = ([self.read_side(frame,i) for i in range(2)] if self.geometry_ok(frame)
                    else [{'raw':'', 'current':None, 'reason':'layout_or_occlusion'} for _ in range(2)])
            side_ms = (self.clock()-begin)*1000
            combined = [combine(r,s,True,g.maximum) for r,s,g in zip(readings,side,self.guards)]
            self.conflict_pending = any(r['verification'] == 'conflict' for r in combined)
            if any(r['verification'] != 'current_agrees' for r in combined):
                self.fast_until = started+2.
            self.next_check = started + (.1 if started < self.fast_until else .5)
        else:
            combined = [combine(r,None,False) for r in readings]
        analysis.update(readings=combined, side_ms=side_ms, side_checked=due,
                        total_ms=(self.clock()-started)*1000)
        return analysis
