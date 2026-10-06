"""Same-frame text verification. Never propagate verification across frames."""
import re
import time

import cv2
import numpy as np
from test_side_counters import locate
from benchmark_hp_mp import crop_bar
from bar_fill import FillEvidence, validate_fill
from glyph_ocr import read_digits
from source_selection import select_source


def side_image(crop):
    """Tight whole-number crop; keep every bright component, not a fixed digit count."""
    if crop.size == 0:
        return np.full((32, 32), 255, dtype=np.uint8)
    gray = crop.min(axis=2)
    large = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    y, x = np.where(large > 140)
    if not len(x):
        return np.full((32, 32), 255, dtype=np.uint8)
    binary = np.where(large > 120, 0, 255).astype('uint8')
    binary = binary[y.min():y.max()+1, x.min():x.max()+1]
    return cv2.copyMakeBorder(binary, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)


def recognize_side(engine, crop, glyph_retry=False):
    """Require one OCR digit per separated ink group; never infer omitted digits."""
    image = side_image(crop)
    columns = np.any(image < 128, axis=0)
    transitions = np.diff(np.r_[False, columns, False].astype(np.int8))
    count = int(np.count_nonzero(transitions == 1))
    raw = engine.recognize(image, psm=8).txts[0].strip()
    result = {'raw': raw, 'current': None, 'visible_digit_groups': count}
    if not re.fullmatch(r'[0-9]+', raw):
        result['reason'] = 'unreadable'
    elif not count or len(raw) != count:
        # Split/broken glyphs may also cause rejection. Prefer unavailable data
        # over silently accepting a shortened number while the top is covered.
        result['reason'] = 'digit_count_mismatch'
    else:
        result['current'] = int(raw)
    if glyph_retry and crop.size:
        # Counter glyphs/background are neutral gray. Colored item icons are
        # foreign content even when their bright edges resemble valid digits.
        low = crop.min(axis=2).astype(np.int16)
        high = crop.max(axis=2).astype(np.int16)
        colored = int(np.count_nonzero((high-low > 45) & (high > 80)))
        result['foreign_color_pixels'] = colored
        if colored >= max(4,crop.shape[0]*crop.shape[1]*.01):
            result.update(current=None,reason='foreign_color_overlay')
            return result
    if glyph_retry and result['current'] is None and count:
        recovery = read_digits(engine, image)
        result['glyph_recovery'] = recovery
        if recovery['text'] is not None and len(recovery['text']) == count:
            result.update(current=int(recovery['text']), reason=None, method='separate_glyphs')
    return result


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


class ConfirmationGate:
    """Two consecutive same-frame agreements; observations are not action values."""
    def __init__(self, max_gap=.25, allow_color_supported=False):
        self.previous = None
        self.max_gap = max_gap
        self.allow_color_supported = allow_color_supported
        self.previous_verified_pair = False

    def apply(self, reading, now):
        result = dict(reading)
        value = reading.get('value')
        supported = reading.get('verification') == 'current_agrees'
        if self.allow_color_supported:
            supported = (reading.get('verification') in ('current_agrees','top_color_supported','side_color_supported')
                         and reading.get('fill_status') == 'consistent')
            supported = supported or (reading.get('verification') == 'current_agrees_without_color'
                                      and reading.get('fill_status') == 'unavailable')
        if not supported or value is None:
            self.previous = None
            self.previous_verified_pair = False
            result.update(candidate_value=value or reading.get('candidate_value'), value=None, quality='unconfirmed',
                          confirmation='sources_not_agreed')
            return result
        key = (value['current'], value['maximum'],
               reading.get('source') if self.allow_color_supported else None,
               value.get('last_confirmed_maximum') if self.allow_color_supported else None)
        previous = self.previous
        previous_pair = self.previous_verified_pair
        verified_pair = (reading.get('verification') == 'current_agrees'
                         and reading.get('fill_status') == 'consistent')
        self.previous = (key, now)
        self.previous_verified_pair = verified_pair
        trusted_change = (self.allow_color_supported and previous and previous_pair and verified_pair
                          and previous[0][1:] == key[1:])
        if previous and (previous[0] == key or trusted_change) and 0 < now-previous[1] <= self.max_gap:
            result['confirmation'] = ('two_frames_agree' if previous[0] == key
                                      else 'two_frames_consistent_change')
        else:
            if previous is None:
                reason='no_previous_candidate'
            elif now <= previous[1]:
                reason='non_monotonic_time'
            elif now-previous[1] > self.max_gap:
                reason='sample_gap'
            elif previous[0][0] != key[0]:
                reason='current_changed'
            elif previous[0][1] != key[1]:
                reason='maximum_or_quality_changed'
            else:
                reason='source_or_cached_maximum_changed'
            result.update(candidate_value=value, value=None, quality='unconfirmed',
                          confirmation='waiting_second_frame',confirmation_reset_reason=reason)
        return result


class DualAnalyzer:
    def __init__(self, top_analyzer, clock=time.perf_counter, strict=False, resilient=False):
        self.top = top_analyzer
        self.engine = top_analyzer.engine
        self.clock = clock
        self.boxes = None
        self.next_check = 0.
        self.fast_until = 0.
        self.conflict_pending = False
        self.strict = strict
        self.resilient = resilient
        self.confirmations = [ConfirmationGate(allow_color_supported=resilient) for _ in range(2)]

    def read_side(self, frame, index):
        x,y,w,h = self.boxes[index]
        return recognize_side(self.engine, frame[y:y+h, x:x+w], glyph_retry=self.resilient)

    def calibrate(self, frame, readings, guards):
        self.boxes, bars = locate(frame, return_bars=True)
        self.side_bars = bars
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
        self.fill_models = [
            {'top':FillEvidence(crop_bar(frame,self.top.rectangles[i]), resource),
             'sidebar':FillEvidence(crop_bar(frame,self.side_bars[i]), resource, sidebar=True)}
            for i,resource in enumerate(('hp','mp'))]
        cadence = 'kazda klatka + potwierdzenie kolejnej' if self.strict else '2/s'
        print(f'Boczne HP/MP: {self.boxes}; zgodne z gora. Weryfikacja {cadence}.', flush=True)
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
        due = self.strict or self.resilient or self.conflict_pending or started >= self.next_check or any(r['value'] is None for r in readings)
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
        if self.strict or self.resilient:
            evidence = [{
                'top':self.fill_models[i]['top'].measure(crop_bar(frame,self.top.rectangles[i])),
                'sidebar':self.fill_models[i]['sidebar'].measure(crop_bar(frame,self.side_bars[i]))}
                for i in range(2)]
            if self.resilient:
                combined = [select_source(r,s,e,g.maximum)
                            for r,s,e,g in zip(readings,side,evidence,self.guards)]
            else:
                combined = [validate_fill(r,e) for r,e in zip(combined,evidence)]
            now = self.clock()
            combined = [gate.apply(r, now) for gate, r in zip(self.confirmations, combined)]
        analysis.update(readings=combined, side_ms=side_ms, side_checked=due,
                        total_ms=(self.clock()-started)*1000)
        return analysis
