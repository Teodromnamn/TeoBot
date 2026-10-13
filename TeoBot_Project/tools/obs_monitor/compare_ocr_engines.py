"""Offline comparison on identical saved HP/MP crops; Windows Python 3.10+.
Tesseract CLI timings include launching two processes; not a resident API test.
Valid syntax is not verified accuracy. Inspect input.png and raw outputs.
"""
import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from benchmark_hp_mp import crop_bar, prepare


def child_cpu(process):
    if os.name != 'nt':
        return None
    from ctypes import wintypes
    f=ctypes.windll.kernel32.GetProcessTimes
    f.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    f.restype=wintypes.BOOL
    a,b,k,u=[wintypes.FILETIME() for _ in range(4)]
    if not f(int(process._handle),ctypes.byref(a),ctypes.byref(b),ctypes.byref(k),ctypes.byref(u)):
        return None
    return ((k.dwHighDateTime<<32)+k.dwLowDateTime+(u.dwHighDateTime<<32)+u.dwLowDateTime)/1e7


def tess(exe,path):
    env=os.environ.copy()
    env['OMP_THREAD_LIMIT']='2'
    p=subprocess.Popen([exe,str(path),'stdout','-l','eng','--psm','7',
                        '-c','tessedit_char_whitelist=0123456789/()'],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    try:
        out,err=p.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        p.kill();p.communicate();raise
    cpu=child_cpu(p)
    if p.returncode:
        raise RuntimeError(err.decode('utf-8',errors='replace'))
    return out.decode('utf-8',errors='replace').strip(),cpu


def worker(args):
    folder=Path(args.output)
    crops=[cv2.imread(str(folder/f'{name}.png')) for name in ('hp','mp')]
    paths=[folder/f'{name}.png' for name in ('hp','mp')]
    engine=None
    if not args.worker.startswith('tesseract'):
        from rapidocr import RapidOCR,LangRec,OCRVersion,ModelType
        params={'EngineConfig.onnxruntime.intra_op_num_threads':args.threads,
                'EngineConfig.onnxruntime.inter_op_num_threads':1}
        if args.worker!='rapid_default':
            params.update({'Rec.lang_type':LangRec.EN,'Rec.model_type':ModelType.MOBILE,
                           'Rec.ocr_version':OCRVersion.PPOCRV4 if args.worker=='rapid_en_v4' else OCRVersion.PPOCRV5})
        engine=RapidOCR(params=params)
    elif args.worker=='tesseract_binary':
        paths=[]
        for name,img in zip(('hp','mp'),crops):
            low=img.min(axis=2).astype(np.int16)
            high=img.max(axis=2).astype(np.int16)
            binary=np.where((low>=140)&(high-low<=65),0,255).astype('uint8')
            p=folder/f'{name}_binary.png';cv2.imwrite(str(p),binary);paths.append(p)
    times=[];cpus=[];outputs=[]
    cv2.setNumThreads(1)
    for n in range(args.runs+1):
        start=time.perf_counter();cpu_start=time.process_time();children=0.;cpu_known=True
        raw=[]
        for img,path in zip(crops,paths):
            if engine is not None:
                result=engine(img,use_det=False,use_cls=False,use_rec=True)
                raw.append(list(result.txts) if result.txts is not None else [])
            else:
                text,cpu=tess(args.tesseract,path);raw.append([text])
                if cpu is None:cpu_known=False
                else:children+=cpu
        elapsed=(time.perf_counter()-start)*1000
        cpu_ms=(time.process_time()-cpu_start+children)*1000 if cpu_known else None
        print(f'{args.worker} {n}/{args.runs}: {elapsed:.1f} ms {raw}',flush=True)
        if n:
            times.append(elapsed);cpus.append(cpu_ms);outputs.append(raw)
    report={'variant':args.worker,'median_ms':float(np.median(times)),
            'p95_ms':float(np.percentile(times,95)),
            'cpu_ms_per_pair_median':float(np.median(cpus)) if all(c is not None for c in cpus) else None,
            'outputs':outputs,'threads':args.threads,
            'note':'Tesseract CLI includes process startup; inspect raw readings for correctness.'}
    (folder/f'{args.worker}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',help='Optional image; otherwise newest pipeline calibration is used')
    p.add_argument('--runs',type=int,default=10)
    p.add_argument('--threads',type=int,default=2)
    p.add_argument('--tesseract',default=shutil.which('tesseract') or r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    p.add_argument('--output',default='ocr_comparison_'+time.strftime('%Y%m%d_%H%M%S'))
    p.add_argument('--worker',choices=['rapid_default','rapid_en_v4','rapid_en_v5','tesseract_color','tesseract_binary'])
    args=p.parse_args()
    if args.runs<1 or args.threads<1:p.error('runs and threads must be positive')
    if args.worker:return worker(args)
    folder=Path(args.output).resolve();folder.mkdir(parents=True,exist_ok=True)
    if args.image:
        source=Path(args.image)
    else:
        candidates=list(Path('obs_fast_results').glob('*/calibration.png'))
        if not candidates:raise RuntimeError('Brak calibration.png. Podaj --image sciezka_do_zrzutu')
        source=max(candidates,key=lambda x:x.stat().st_mtime)
    image=cv2.imdecode(np.fromfile(source,dtype=np.uint8),1)
    if image is None:raise RuntimeError(f'Nie mozna otworzyc {source}')
    calibration=source.with_suffix('.json')
    if calibration.exists():
        pair=json.loads(calibration.read_text(encoding='utf-8'))['rectangles']
    else:
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        from game.status_bar_detector import _tibia_top_pair
        pair=_tibia_top_pair(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
    if pair is None:raise RuntimeError('Brak paskow; uzyj obrazu calibration.png z testu pipeline')
    cv2.imencode('.png',image)[1].tofile(folder/'input.png')
    for name,rect in zip(('hp','mp'),pair):
        crop=prepare(crop_bar(image,rect),'dynamic')
        cv2.imencode('.png',crop)[1].tofile(folder/f'{name}.png')
    print(f'Obraz: {source}\nWycinki: {folder}\nPierwsze uruchomienie moze pobrac modele.',flush=True)
    reports=[]
    for variant in ['rapid_default','rapid_en_v4','rapid_en_v5','tesseract_color','tesseract_binary']:
        if variant.startswith('tesseract') and not Path(args.tesseract).is_file():
            reports.append({'variant':variant,'error':'Tesseract not found; use --tesseract path'});continue
        command=[sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--worker',variant,
                 '--output',str(folder),'--runs',str(args.runs),'--threads',str(args.threads),'--tesseract',args.tesseract]
        try:
            subprocess.run(command,check=True,timeout=600)
            reports.append(json.loads((folder/f'{variant}.json').read_text(encoding='utf-8')))
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
            reports.append({'variant':variant,'error':str(e)})
    (folder/'summary.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    print('\nPODSUMOWANIE:')
    for r in reports:print({k:v for k,v in r.items() if k!='outputs'})
    print(f'Wyslij {folder / "summary.json"}. To test statyczny, nie dowod odpornosci na zmiane skali.')


if __name__=='__main__':
    main()
