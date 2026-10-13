"""Resident Tesseract C API benchmark. No subprocess per image, no new packages.
Uses hp.png/mp.png from the latest ocr_comparison folder, or --input DIR.
Tesseract API is single-owner: do not call the same instance concurrently.
"""
import argparse
import ctypes as C
import ctypes.util
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np


class ResidentTesseract:
    def __init__(self, directory, tessdata=None):
        self.api=None
        self.dll_directory=None
        if os.name=='nt':
            directory=Path(directory).resolve()
            self.dll_directory=os.add_dll_directory(str(directory))
            library=str(directory/'libtesseract-5.dll')
            tessdata=tessdata or str(directory/'tessdata')
        else:
            library=ctypes.util.find_library('tesseract')
        self.lib=C.CDLL(library)
        def bind(name,result,args):
            f=getattr(self.lib,name);f.restype=result;f.argtypes=args;return f
        ptr=C.c_void_p
        self.create=bind('TessBaseAPICreate',ptr,[])
        self.delete=bind('TessBaseAPIDelete',None,[ptr])
        self.init=bind('TessBaseAPIInit3',C.c_int,[ptr,C.c_char_p,C.c_char_p])
        self.variable=bind('TessBaseAPISetVariable',C.c_int,[ptr,C.c_char_p,C.c_char_p])
        self.psm=bind('TessBaseAPISetPageSegMode',None,[ptr,C.c_int])
        self.set_image=bind('TessBaseAPISetImage',None,[ptr,ptr,C.c_int,C.c_int,C.c_int,C.c_int])
        self.recognize=bind('TessBaseAPIRecognize',C.c_int,[ptr,ptr])
        self.get_text=bind('TessBaseAPIGetUTF8Text',ptr,[ptr])
        self.free_text=bind('TessDeleteText',None,[ptr])
        self.clear=bind('TessBaseAPIClear',None,[ptr])
        self.clear_adaptive=bind('TessBaseAPIClearAdaptiveClassifier',None,[ptr])
        self.version=bind('TessVersion',C.c_char_p,[])().decode()
        self.api=self.create()
        if not self.api:raise RuntimeError('TessBaseAPICreate failed')
        try:
            if self.init(self.api,str(tessdata).encode('utf-8') if tessdata else None,b'eng'):
                raise RuntimeError('Cannot load eng.traineddata. Check --tessdata directory.')
            self.psm(self.api,7)
            if not self.variable(self.api,b'tessedit_char_whitelist',b'0123456789/()'):
                raise RuntimeError('Cannot set digit whitelist')
        except Exception:
            self.close();raise

    def read(self,image):
        image=np.ascontiguousarray(image,dtype=np.uint8)
        h,w=image.shape[:2]
        channels=1 if image.ndim==2 else image.shape[2]
        if channels not in (1,3):raise ValueError('Expected grayscale or RGB')
        try:
            self.set_image(self.api,image.ctypes.data,w,h,channels,image.strides[0])
            if self.recognize(self.api,None):raise RuntimeError('Recognition failed')
            text=self.get_text(self.api)
            if not text:return ''
            try:return C.string_at(text).decode('utf-8').strip()
            finally:self.free_text(text)
        finally:
            self.clear(self.api)
            # Prevent identical benchmark images benefiting from adaptive memory.
            self.clear_adaptive(self.api)

    def close(self):
        if self.api:
            self.delete(self.api);self.api=None
        if self.dll_directory:
            self.dll_directory.close();self.dll_directory=None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path)
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
    p.add_argument('--tessdata')
    p.add_argument('--runs',type=int,default=10)
    p.add_argument('--threads',type=int,default=2)
    args=p.parse_args()
    if min(args.runs,args.threads)<1:p.error('runs and threads must be positive')
    os.environ['OMP_THREAD_LIMIT']=str(args.threads)
    cv2.setNumThreads(1)
    folder=args.input
    if folder is None:
        candidates=[d for d in Path('.').glob('ocr_comparison_*') if (d/'hp.png').is_file() and (d/'mp.png').is_file()]
        if not candidates:raise RuntimeError('No saved crops. Run compare_ocr_engines.py first or use --input DIR.')
        folder=max(candidates,key=lambda d:d.stat().st_mtime)
    images=[]
    for name in ('hp','mp'):
        a=cv2.imdecode(np.fromfile(folder/f'{name}.png',dtype=np.uint8),1)
        if a is None:raise RuntimeError(f'Cannot read {name}.png')
        images.append(a)
    variants={'color':[cv2.cvtColor(a,cv2.COLOR_BGR2RGB) for a in images],
              'binary':[np.where((a.min(axis=2)>=140)&
                        (a.max(axis=2).astype(np.int16)-a.min(axis=2)<=65),0,255).astype('uint8') for a in images]}
    start=time.perf_counter();engine=ResidentTesseract(args.directory,args.tessdata)
    init_ms=(time.perf_counter()-start)*1000
    reports={key:[] for key in variants}
    print(f'Tesseract {engine.version}; initialization {init_ms:.1f} ms; input {folder}',flush=True)
    try:
        for key in ['color','binary','binary','color']:
            for image in variants[key]:engine.read(image) # unmeasured warmup
            for n in range(args.runs):
                cpu=time.process_time();start=time.perf_counter()
                texts=[engine.read(a) for a in variants[key]]
                ms=(time.perf_counter()-start)*1000
                cpu_ms=(time.process_time()-cpu)*1000
                reports[key].append({'ms':ms,'cpu_ms':cpu_ms,'texts':texts})
            print(f'{key}: last={ms:.1f} ms, {texts}',flush=True)
    finally:
        engine.close()
    result={'version':engine.version,'initialization_ms':init_ms,'input':str(folder),
            'threads':args.threads,'variants':{},'note':'Same saved crops, resident C API, explicit recognition and cleanup. No accuracy ground truth.'}
    for key,rows in reports.items():
        result['variants'][key]={'median_ms':float(np.median([r['ms'] for r in rows])),
                                'p95_ms':float(np.percentile([r['ms'] for r in rows],95)),
                                'cpu_ms_per_pair_median':float(np.median([r['cpu_ms'] for r in rows])),
                                'samples':rows}
    output=folder/('tesseract_resident_'+time.strftime('%Y%m%d_%H%M%S')+'.json')
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PODSUMOWANIE:')
    for key,r in result['variants'].items():print(key,{k:v for k,v in r.items() if k!='samples'},'last:',r['samples'][-1]['texts'])
    print(f'Zapisano: {output}')


if __name__=='__main__':
    main()
