"""Compare the same saved crops, same sizes, different preprocessing and engines.
Each worker loads its engine once; loading and warmup excluded from timings.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

VARIANTS=['rapid_color','rapid_black_on_white','rapid_white_on_black','tesseract_binary']


def prepare_image(image,variant):
    if variant=='rapid_color':return image.copy()
    low=image.min(axis=2).astype(np.int16)
    high=image.max(axis=2).astype(np.int16)
    white=(low>=140)&(high-low<=65)
    binary=np.where(white,255 if variant=='rapid_white_on_black' else 0,
                    0 if variant=='rapid_white_on_black' else 255).astype('uint8')
    return cv2.cvtColor(binary,cv2.COLOR_GRAY2BGR) if variant.startswith('rapid') else binary


def worker(args):
    images=[cv2.imdecode(np.fromfile(args.input/f'{name}.png',dtype=np.uint8),1) for name in ['hp','mp']]
    if any(a is None for a in images):raise RuntimeError('Cannot read HP/MP crops')
    if args.variant.startswith('rapid'):
        from rapidocr import RapidOCR
        engine=RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':args.threads,
                               'EngineConfig.onnxruntime.inter_op_num_threads':1})
        def read(image):
            result=engine(image,use_det=False,use_cls=False,use_rec=True)
            return list(result.txts) if result.txts is not None else []
    else:
        from test_tesseract_resident import ResidentTesseract
        os.environ['OMP_THREAD_LIMIT']=str(args.threads)
        engine=ResidentTesseract(args.directory)
        def read(image):return [engine.read(image)]
    rows=[]
    try:
        for name,a in zip(['hp','mp'],images):
            cv2.imencode('.png',prepare_image(a,args.variant))[1].tofile(args.output/f'{args.variant}_{name}.png')
        for n in range(args.runs+2):
            cpu=time.process_time();start=time.perf_counter()
            crops=[prepare_image(a,args.variant) for a in images]
            prepared=time.perf_counter()
            texts=[read(a) for a in crops]
            done=time.perf_counter()
            row={'prepare_ms':(prepared-start)*1000,'recognition_ms':(done-prepared)*1000,
                 'total_ms':(done-start)*1000,'cpu_ms':(time.process_time()-cpu)*1000,'texts':texts}
            if n>=2:rows.append(row)
        report={'variant':args.variant,'round':args.round,'rows':rows}
        (args.output/f'{args.variant}_{args.round}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(args.variant,'last:',texts,flush=True)
    finally:
        if args.variant=='tesseract_binary':engine.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path)
    p.add_argument('--output',type=Path,default=Path('binary_comparison_'+time.strftime('%Y%m%d_%H%M%S')))
    p.add_argument('--threads',type=int,default=2)
    p.add_argument('--runs',type=int,default=10)
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
    p.add_argument('--variant',choices=VARIANTS)
    p.add_argument('--round',type=int,default=0)
    args=p.parse_args()
    if min(args.runs,args.threads)<1:p.error('Positive runs and threads required')
    cv2.setNumThreads(1)
    if args.variant:return worker(args)
    if args.input is None:
        candidates=[d for d in Path('.').glob('ocr_comparison_*') if (d/'hp.png').is_file() and (d/'mp.png').is_file()]
        if not candidates:raise RuntimeError('No saved crops: use --input folder_with_hp_and_mp_png')
        args.input=max(candidates,key=lambda d:d.stat().st_mtime)
    args.input=args.input.resolve();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    print(f'INPUT: {args.input}',flush=True)
    results={v:[] for v in VARIANTS};errors=[]
    for iteration,order in enumerate([VARIANTS,list(reversed(VARIANTS))]):
        for variant in order:
            command=[sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--variant',variant,
                     '--round',str(iteration),'--input',str(args.input),'--output',str(args.output),
                     '--threads',str(args.threads),'--runs',str(args.runs),'--directory',args.directory]
            try:
                subprocess.run(command,check=True,timeout=300)
                report=json.loads((args.output/f'{variant}_{iteration}.json').read_text(encoding='utf-8'))
                results[variant].extend(report['rows'])
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
                errors.append({'variant':variant,'round':iteration,'error':str(e)})
    summary={'input':str(args.input),'threads':args.threads,'errors':errors,'variants':{}}
    for variant,rows in results.items():
        if not rows:continue
        report={k:{'median':float(np.median([r[k] for r in rows])),
                   'p95':float(np.percentile([r[k] for r in rows],95))}
                for k in ['prepare_ms','recognition_ms','total_ms','cpu_ms']}
        report['outputs']=[r['texts'] for r in rows]
        summary['variants'][variant]=report
        print(variant,{k:v for k,v in report.items() if k!='outputs'},'last:',report['outputs'][-1])
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(f'Wyslij: {args.output / "summary.json"}. Sprawdz liczby; ten test nie mierzy odpornosci na zmiane skali.')


if __name__=='__main__':main()
