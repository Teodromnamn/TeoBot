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
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from benchmark_hp_mp import crop_bar,prepare,parse_output
from test_tesseract_resident import ResidentTesseract
from glyph_ocr import recover_ratio
import test_obs_pipeline as pipeline


def binary(image):
    # Keep tinted anti-aliased edges: benchmark variant min_threshold_120.
    low=image.min(axis=2)
    return np.where(low>=120,0,255).astype('uint8')


class Engine:
    def __init__(self,directory,cache_limit=128):
        from ocr_cache import PixelCache
        self.cache=PixelCache(limit=cache_limit)
        self.tess=ResidentTesseract(directory)
        # Read confidence before ResidentTesseract clears the page.
        self.mean_conf=self.tess.lib.TessBaseAPIMeanTextConf
        self.mean_conf.restype=C.c_int
        self.mean_conf.argtypes=[C.c_void_p]

    def recognize(self,image,psm=7):
        return self.cache.recognize(image,psm,self._recognize)

    def _recognize(self,image,psm=7):
        image=np.ascontiguousarray(image,dtype=np.uint8)
        h,w=image.shape
        t=self.tess
        try:
            t.psm(t.api,psm)
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
            t.psm(t.api,7)

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


def recognize_top(engine, image, glyph_retry=False, raw_crop=None, resource=None):
    evidence=None
    if glyph_retry and raw_crop is not None:
        from text_occlusion import inspect_top_text,unavailable
        evidence=inspect_top_text(raw_crop,resource)
        if evidence['occluded']:return unavailable(evidence)
    result = parse_reading(engine.recognize(image))
    if evidence is not None:result['text_occlusion']=evidence
    if glyph_retry and result['value'] is None:
        recovery = recover_ratio(engine, image)
        result['glyph_recovery'] = recovery
        if recovery['text'] is not None:
            recovered = parse_reading(SimpleNamespace(txts=[recovery['text']], scores=[0.]))
            if recovered['value'] is not None:
                result.update(value=recovered['value'], method='visual_separator_and_glyphs')
    return result


class Analyzer:
    def __init__(self,engine,rectangles,glyph_retry=False):
        self.engine,self.rectangles=engine,rectangles
        self.glyph_retry=glyph_retry

    def analyze(self,frame):
        start=time.perf_counter()
        raw_crops=[crop_bar(frame,r) for r in self.rectangles]
        from text_occlusion import inspect_top_text,unavailable
        overlays=[inspect_top_text(c,resource) if self.glyph_retry else {'occluded':False} for c,resource in zip(raw_crops,('hp','mp'))]
        crops=[None if e['occluded'] else binary(prepare(c,'dynamic')) for c,e in zip(raw_crops,overlays)]
        prepared=time.perf_counter()
        results=[unavailable(e) if e['occluded'] else dict(recognize_top(self.engine,c,self.glyph_retry),text_occlusion=e) for c,e in zip(crops,overlays)]
        recognized=time.perf_counter()
        return {'readings':results,
                'prepare_ms':(prepared-start)*1000,
                'recognition_ms':(recognized-prepared)*1000,
                'total_ms':(time.perf_counter()-start)*1000,
                'crop_sizes':[(c.shape[1],c.shape[0]) if c is not None else (0,0) for c in crops]}


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
    parser.add_argument('--verify-side', action='store_true', help='Porownuj boczne liczniki 2/s na tej samej klatce')
    parser.add_argument('--capture-conflicts', action='store_true', help='Zapisz ograniczona paczke wycinkow przy konflikcie (wymaga --verify-side)')
    parser.add_argument('--capture-dataset', action='store_true', help='Zapisuj surowe wycinki obu zrodel i paskow do ZIP, 5/s, maks. 2000 probek')
    parser.add_argument('--strict-verification', action='store_true', help='Wymagaj zgodnosci obu OCR w kazdej klatce i dwoch kolejnych zgodnych par')
    parser.add_argument('--resilient-verification', action='store_true', help='Eksperymentalnie: OCR cyfr osobno, wybor zrodla wsparty kolorem i dwiema klatkami')
    parser.add_argument('--threads',type=int,choices=[1,2,4],default=2)
    parser.add_argument('--no-ocr-cache',action='store_true',help='Wylacz pamiec identycznych wycinkow do porownania czasu')
    args,remaining=parser.parse_known_args()
    if args.capture_dataset or args.strict_verification or args.resilient_verification:
        args.verify_side = True
    if args.strict_verification and args.resilient_verification:
        parser.error('Wybierz strict-verification LUB resilient-verification')
    if args.capture_conflicts and not args.verify_side:
        parser.error('--capture-conflicts wymaga --verify-side')
    if '--retune' in remaining:
        raise SystemExit('Ten test Tesseracta nie uzywa Auto. Ustaw --threads 1, 2 lub 4.')
    if '--help' in remaining or '-h' in remaining:
        print(__doc__+'\nDodatkowo: --directory SCIEZKA, --threads 1|2|4, --verify-side, '
              '--strict-verification, --resilient-verification, --capture-conflicts, --capture-dataset. Opcje pipeline:')
        sys.argv=[sys.argv[0],'--help']
        pipeline.main()
        return
    os.environ['OMP_THREAD_LIMIT']=str(args.threads)
    engine=Engine(args.directory,cache_limit=0 if args.no_ocr_cache else 128)
    recorder=None
    dataset=None
    if args.capture_conflicts:
        from conflict_capture import ConflictCapture
        recorder=ConflictCapture(Path('ocr_conflicts_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
        print('Diagnostyka konfliktow: maks. 60 przypadkow; zapis PNG doliczany do czasu analizy.', flush=True)
    if args.capture_dataset:
        from dataset_capture import DatasetCapture
        dataset=DatasetCapture(Path('ocr_dataset_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
        print('Dataset: surowe PNG 5/s; zapis doliczany do czasu analizy. OCR nie jest etykieta.', flush=True)
    original_factory,original_analyzer,original_parser=pipeline.make_engine,pipeline.HpMpAnalyzer,pipeline.parse_output
    original_argv=sys.argv
    try:
        # Keep exactly one API alive, including calibration and measured run.
        pipeline.make_engine=lambda threads:engine
        if args.verify_side:
            from dual_source import DualAnalyzer
            class RecordingDualAnalyzer(DualAnalyzer):
                def calibrate(self, frame, readings, guards):
                    result=super().calibrate(frame,readings,guards)
                    if dataset is not None:
                        dataset.calibrate(frame,self.top.rectangles,self.side_bars)
                    return result
                def analyze(self, frame):
                    result=super().analyze(frame)
                    if recorder is not None:
                        begin=time.perf_counter()
                        recorder.capture(frame,result,self.top.rectangles,self.boxes,binary)
                        result['diagnostic_ms']=(time.perf_counter()-begin)*1000
                    if dataset is not None:
                        begin=time.perf_counter()
                        dataset.capture(frame,result,self.top.rectangles,self.boxes,self.side_bars)
                        result['dataset_ms']=(time.perf_counter()-begin)*1000
                    return result
            pipeline.HpMpAnalyzer=lambda engine, rectangles: RecordingDualAnalyzer(Analyzer(engine, rectangles, glyph_retry=args.resilient_verification), strict=args.strict_verification, resilient=args.resilient_verification)
        else:
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
        if recorder is not None:
            recorder.finish()
        if dataset is not None:
            dataset.finish()


if __name__=='__main__':
    try:
        if '--dashboard' in sys.argv:
            sys.argv.remove('--dashboard')
            from monitor_dashboard import run_dashboard
            run_dashboard(main, pipeline)
        else:
            main()
    except KeyboardInterrupt:print('Przerwano.')
