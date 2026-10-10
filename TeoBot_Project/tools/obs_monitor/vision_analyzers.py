"""Independent analyzers. Input is the full BGR frame; never mutate it.

Locations are image coordinates. A future BattleListAnalyzer can use the same
analyze(frame) interface and share an OCR engine, without another camera.
"""
import time
import cv2
from benchmark_hp_mp import crop_bar, prepare, parse_output


class HpMpAnalyzer:
    def __init__(self, engine, rectangles):
        self.engine = engine
        self.rectangles = rectangles

    def analyze(self, frame):
        start = time.perf_counter()
        crops = [prepare(crop_bar(frame, rect), 'dynamic') for rect in self.rectangles]
        prepared = time.perf_counter()
        results = [self.engine(crop, use_det=False, use_cls=False, use_rec=True) for crop in crops]
        recognized = time.perf_counter()
        readings = [parse_output(result) for result in results]
        return {'readings': readings, 'prepare_ms': (prepared-start)*1000,
                'recognition_ms': (recognized-prepared)*1000,
                'total_ms': (time.perf_counter()-start)*1000,
                'crop_sizes': [(c.shape[1], c.shape[0]) for c in crops]}


class TemplateAnalyzer:
    """Optional same-scale template locator, not a Battle List detector.

    Supply an icon image cropped from the same UI scale. Text recognition and
    panel bounds must independently confirm a candidate before it is used.
    """
    def __init__(self, template_bgr, threshold=.9, region=None):
        self.template = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        if self.template.std() < 1:
            raise ValueError('Template must contain visible detail')
        self.threshold, self.region = threshold, region

    def analyze(self, frame):
        x,y,w,h = self.region or (0,0,frame.shape[1],frame.shape[0])
        gray = cv2.cvtColor(crop_bar(frame,(x,y,w,h)), cv2.COLOR_BGR2GRAY)
        th,tw = self.template.shape
        if gray.shape[0]<th or gray.shape[1]<tw:
            return {'candidate':None}
        response = cv2.matchTemplate(gray,self.template,cv2.TM_CCOEFF_NORMED)
        _,score,_,location = cv2.minMaxLoc(response)
        return {'candidate': (x+location[0],y+location[1],tw,th) if score>=self.threshold else None,
                'score':float(score)}
