"""Offline preprocessing comparison on captured cases. No automatic OCR correction.
Reads ZIP members without extraction. Original OCR is context, NOT ground truth.
"""
import argparse
import csv
import html
import io
import json
import os
import re
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np
from test_tesseract_resident import ResidentTesseract


def variants(original, prepared, previous):
    # First alternatives use exactly the old crop, isolating threshold effects.
    minimum = prepared.min(axis=2)
    yield 'baseline', previous
    yield 'min_gray', 255-minimum
    _, otsu = cv2.threshold(minimum, 0, 255, cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    yield 'min_otsu', otsu
    yield 'min_threshold_120', np.where(minimum>=120,0,255).astype('uint8')
    # Alternate route: isolate bright text on the ORIGINAL bar, before resizing.
    # No "almost gray" constraint; search full bar width on each image.
    source = original.min(axis=2)
    interior = source[1:-1,1:-1] if min(source.shape)>4 else source
    ys,xs = np.where(interior>=140)
    if len(xs):
        x0,x1 = max(0,int(xs.min())-2),min(interior.shape[1],int(xs.max())+3)
        y0,y1 = max(0,int(ys.min())-1),min(interior.shape[0],int(ys.max())+2)
        source = interior[y0:y1,x0:x1]
    else:
        source = interior
    nearest = cv2.resize(source,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
    gray = cv2.copyMakeBorder(255-nearest,6,6,12,12,cv2.BORDER_CONSTANT,value=255)
    yield 'original_nearest_gray', gray
    _, native = cv2.threshold(source,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    native = cv2.resize(native,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
    yield 'original_otsu_nearest', cv2.copyMakeBorder(native,6,6,12,12,cv2.BORDER_CONSTANT,value=255)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path)
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
    p.add_argument('--limit',type=int,default=100)
    args=p.parse_args()
    if args.limit<1:p.error('--limit must be positive')
    if args.input is None:
        found=list(Path('.').glob('ocr_cases_*.zip'))
        if not found:raise RuntimeError('No ocr_cases ZIP: specify --input path')
        args.input=max(found,key=lambda f:f.stat().st_mtime)
    os.environ['OMP_THREAD_LIMIT']='2'
    cv2.setNumThreads(1)
    output=Path('preprocess_results_'+time.strftime('%Y%m%d_%H%M%S'))
    output.mkdir()
    rows=[]; previews=[]
    engine=ResidentTesseract(args.directory)
    try:
        with zipfile.ZipFile(args.input) as archive:
            names=set(archive.namelist())
            cases=sorted(n[:-len('reading.json')] for n in names if n.endswith('/reading.json'))[:args.limit]
            if not cases:raise RuntimeError('ZIP contains no case reading.json files')
            def load(name,color):
                info=archive.getinfo(name)
                if info.file_size>10_000_000:raise ValueError('Image unexpectedly large')
                img=cv2.imdecode(np.frombuffer(archive.read(name),dtype=np.uint8),color)
                if img is None:raise ValueError('Invalid image: '+name)
                return img
            for index,case in enumerate(cases):
                meta=json.loads(archive.read(case+'reading.json'))
                for resource_index,resource in enumerate(('hp','mp')):
                    original=load(case+resource+'_original.png',cv2.IMREAD_COLOR)
                    prepared=load(case+resource+'_prepared.png',cv2.IMREAD_COLOR)
                    previous=load(case+resource+'_binary.png',cv2.IMREAD_GRAYSCALE)
                    base=f'{index:03d}_{resource}'
                    cv2.imencode('.png',original)[1].tofile(output/(base+'_original.png'))
                    previews.append('<h3>'+html.escape(case+' '+resource)+'</h3><img src="'+base+'_original.png"><table>')
                    candidates=list(variants(original,prepared,previous))
                    # Alternate processing order to reduce systematic ordering effects.
                    if index%2:candidates.reverse()
                    for name,img in candidates:
                        if not rows:engine.read(img) # warm up before first measurement
                        start=time.perf_counter()
                        text=engine.read(img)
                        elapsed=(time.perf_counter()-start)*1000
                        match=re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)(?:\s*\([^)]*\))?\s*',text)
                        current,maximum=map(int,match.groups()) if match else (None,None)
                        plausible=maximum is not None and maximum>0 and 0<=current<=maximum
                        filename=base+'_'+name+'.png'
                        cv2.imencode('.png',img)[1].tofile(output/filename)
                        rows.append({'case':case,'resource':resource,'variant':name,'text':text,
                                     'current':current,'maximum':maximum,'plausible':plausible,
                                     'recognition_ms':elapsed,'previous_ocr':json.dumps(meta['readings'][resource_index]),
                                     'image':filename})
                        previews.append('<tr><td>'+name+'</td><td><img src="'+filename+'"></td><td>'+html.escape(text)+'</td></tr>')
                    previews.append('</table>')
                print(f'Przypadek {index+1}/{len(cases)}',flush=True)
    finally:
        engine.close()
    with (output/'readings.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={'input':str(args.input),'cases':len(cases),'variants':{},
             'note':'Plausible format is NOT accuracy. Previous OCR and initial maximum are not labels.'}
    for name in sorted(set(r['variant'] for r in rows)):
        selected=[r for r in rows if r['variant']==name]
        summary['variants'][name]={'readings':len(selected),'plausible':sum(r['plausible'] for r in selected),
          'recognition_median_ms':float(np.median([r['recognition_ms'] for r in selected]))}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'preview.html').write_text('<!doctype html><meta charset="utf-8"><title>OCR comparison</title><style>body{font:16px sans-serif}td{padding:8px;border-bottom:1px solid #ccc}img{max-width:100%}</style><p>Compare against original images; plausible numbers are not verified correct.</p>'+''.join(previews),encoding='utf-8')
    result_zip=output.with_suffix('.zip')
    with zipfile.ZipFile(result_zip,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(output.iterdir()):z.write(f,f.name)
    print(json.dumps(summary,indent=2))
    print('Wyslij: '+str(result_zip))


if __name__=='__main__':
    main()
