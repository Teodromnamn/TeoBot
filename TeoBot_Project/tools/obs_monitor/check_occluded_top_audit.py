"""Offline native audit against independently read sidebar labels.

Accepts the 20261010_200322 long diagnostic ZIP or its inner dataset ZIP.
"""
import argparse
import hashlib
import io
import json
import os
import zipfile
import cv2
import numpy as np
from bar_fill import FillEvidence
from dual_source import recognize_side,side_text_left
from source_selection import select_source
from test_obs_tesseract import Engine

# All distinct sidebar images while top was flagged as covered. Values were
# read visually from original crops, never generated from stored OCR.
REFERENCES=[(351,'mp',39,60),(372,'hp',153,155),(1509,'mp',1,70),
 (1526,'mp',70,70),(1529,'mp',67,70),(1547,'mp',49,70),(1569,'hp',73,165),
 (2094,'hp',170,170),(2100,'mp',27,75),(2382,'mp',6,75),(2399,'mp',3,75),
 (4122,'mp',17,80),(4134,'hp',146,175),(4169,'mp',20,80),(4345,'mp',26,80),
 (4384,'mp',29,80)]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive')
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR' if os.name=='nt' else '/usr/share/tesseract-ocr/5')
    args=p.parse_args();os.environ['OMP_THREAD_LIMIT']='2'
    errors=[];samples=0;seen=set();cache={}
    engine=Engine(args.directory)
    try:
        with zipfile.ZipFile(args.archive) as outer:
            nested=[n for n in outer.namelist() if n.startswith('ocr_dataset_') and n.endswith('.zip')]
            data=zipfile.ZipFile(io.BytesIO(outer.read(nested[0]))) if nested else outer
            def image(path):return cv2.imdecode(np.frombuffer(data.read(path),np.uint8),1)
            def key(case,r):return r,hashlib.sha256(data.read(f'{case}/{r}_side_original.png')).hexdigest()
            expected={key(f'case_{i:05d}',r):(value,maximum) for i,r,value,maximum in REFERENCES}
            models={r:FillEvidence(image(f'calibration/{r}_side_bar.png'),r,sidebar=True) for r in ('hp','mp')}
            left={r:side_text_left(image(f'case_00000/{r}_side_original.png')) for r in ('hp','mp')}
            cases=sorted(n.rsplit('/',1)[0] for n in data.namelist() if n.endswith('/reading.json'))
            for case in cases:
                readings=json.loads(data.read(case+'/reading.json'))['analysis']['readings']
                for ix,r in enumerate(('hp','mp')):
                    reading=readings[ix]
                    if not (reading.get('ocr_skipped') or reading.get('text_occlusion',{}).get('occluded')):continue
                    samples+=1;k=key(case,r);seen.add(k)
                    if k not in expected:
                        errors.append({'case':case,'resource':r,'reason':'needs_manual_label'});continue
                    value,maximum=expected[k]
                    if k not in cache:
                        cache[k]=recognize_side(engine,image(f'{case}/{r}_side_original.png'),True,text_left=left[r])
                    side=cache[k]
                    evidence={'top':{'available':False,'reason':'covered'},
                              'sidebar':models[r].measure(image(f'{case}/{r}_side_bar.png'))}
                    result=select_source({'value':None},side,evidence,maximum)
                    actual=(result.get('value') or {}).get('current')
                    if actual!=value:errors.append({'case':case,'resource':r,'expected':value,'actual':actual})
            if data is not outer:data.close()
    finally:engine.tess.close()
    if samples!=388 or len(seen)!=16:
        errors.append({'reason':'unexpected_audit_coverage','samples':samples,'unique_crops':len(seen)})
    print(json.dumps({'passed':not errors,'labeled_resource_samples':samples,'unique_native_crops':len(seen),
        'errors':errors,'note':'Fresh sidebar OCR, independent visual labels, per-frame native fill checks. Only top-covered subset of this specific dataset.'}))
    return 0 if not errors else 1


if __name__=='__main__':raise SystemExit(main())
