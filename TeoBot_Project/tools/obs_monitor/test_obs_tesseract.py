"""Live HP/MP test using one resident Tesseract instance and binary crops.

Reuses full-frame capture, timestamp validation and expiry from test_obs_pipeline.
This comparison uses a fixed OpenMP limit (default 2); RapidOCR auto tuning is
not applicable to Tesseract. No unchanged-image caching and no input actions.
"""
import argparse
import ctypes as C
import os
import re
import sys
import time
from types import SimpleNamespace

import numpy as np
from benchmark_hp_mp import crop_bar,prepare,parse_output
from test_tesseract_resident import ResidentTesseract
import test_obs_pipeline as pipeline


def binary(image):
    # Keep tinted anti-aliased edges: benchmark variant min_threshold_120.
    low=image.min(axis=2)
    return np.where(low>=120,0,255).astype('uint8')


class Engine:
    def __init__(self,directory):
        self.tess=ResidentTesseract(directory)
        # Read confidence before ResidentTesseract clears the page.
        self.mean_conf=self.tess.lib.TessBaseAPIMeanTextConf
        self.mean_conf.restype=C.c_int
        self.mean_conf.argtypes=[C.c_void_p]

    def recognize(self,image):
        image=np.ascontiguousarray(image,dtype=np.uint8)
        h,w=image.shape
        t=self.tess
        try:
            t.set_image(t.api,image.ctypes.data,w,h,1,image.strides[0])
            if t.recognize(t.api,None):raise RuntimeError('Tesseract recognition failed')
            pointer=t.get_text(t.api)
            try:
                text=C.string_at(pointer).decode('utf-8').strip() if pointer else ''
                score=max(0,min(100,self.mean_conf(t.api)))/100
                return SimpleNamespace(txts=[text],scores=[score])
            finally:
                if pointer:t.free_text(pointer)
        finally:
            t.clear(t.api)
            t.clear_adaptive(t.api)

    def __call__(self,image,**kwargs):
        return self.recognize(binary(image))


def parse_reading(result):
    # Mean confidence includes the unrelated MP suffix and is NOT calibrated
    # like RapidOCR's score. Preserve it for diagnostics; validate numeric syntax.
    raw=result.txts
    # Tesseract sometimes adds one '(' BEFORE the main ratio.
    # Remove only that leading artifact; never search arbitrary tooltip text.
    text=raw[0].strip()
    leading_parenthesis=text.startswith('(')
    if leading_parenthesis:
        text=text[1:].lstrip()
    text=re.sub(r'(?<=\d)[ ,.\u00a0](?=\d)','',text.split('(', 1)[0])
    match=re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*',text)
    value=None
    if match:
        current,maximum=map(int,match.groups())
        if maximum>0 and 0<=current<=maximum:
            value={'current':current,'maximum':maximum,'percent':100*current/maximum,
                   'confidence':result.scores[0]}
    return {'raw':raw,'value':value,
            'leading_parenthesis_ignored':leading_parenthesis}


class Analyzer:
    def __init__(self,engine,rectangles):
        self.engine,self.rectangles=engine,rectangles

    def analyze(self,frame):
        start=time.perf_counter()
        crops=[binary(prepare(crop_bar(frame,r),'dynamic')) for r in self.rectangles]
        prepared=time.perf_counter()
        results=[self.engine.recognize(c) for c in crops]
        recognized=time.perf_counter()
        return {'readings':[parse_reading(r) for r in results],
                'prepare_ms':(prepared-start)*1000,
                'recognition_ms':(recognized-prepared)*1000,
                'total_ms':(time.perf_counter()-start)*1000,
                'crop_sizes':[(c.shape[1],c.shape[0]) for c in crops]}


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
    parser.add_argument('--threads',type=int,choices=[1,2,4],default=2)
    args,remaining=parser.parse_known_args()
    if '--retune' in remaining:
        raise SystemExit('Ten test Tesseracta nie uzywa Auto. Ustaw --threads 1, 2 lub 4.')
    if '--help' in remaining or '-h' in remaining:
        print(__doc__+'\nDodatkowo: --directory SCIEZKA, --threads 1|2|4. Opcje pipeline:')
        sys.argv=[sys.argv[0],'--help']
        pipeline.main()
        return
    os.environ['OMP_THREAD_LIMIT']=str(args.threads)
    engine=Engine(args.directory)
    original_factory,original_analyzer,original_parser=pipeline.make_engine,pipeline.HpMpAnalyzer,pipeline.parse_output
    original_argv=sys.argv
    try:
        # Keep exactly one API alive, including calibration and measured run.
        pipeline.make_engine=lambda threads:engine
        pipeline.HpMpAnalyzer=Analyzer
        pipeline.parse_output=parse_reading
        sys.argv=[sys.argv[0],*remaining,'--threads',str(args.threads)]
        print(f'Tesseract {engine.tess.version}; binary; threads={args.threads}; no OCR cache.',flush=True)
        pipeline.main()
    finally:
        pipeline.make_engine,pipeline.HpMpAnalyzer=original_factory,original_analyzer
        pipeline.parse_output=original_parser
        sys.argv=original_argv
        engine.tess.close()


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Przerwano.')
