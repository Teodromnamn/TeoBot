"""Fresh OCR of 15 visually labeled 224456 conflict frames, without game/OBS."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import zipfile
import cv2
import numpy as np
from benchmark_hp_mp import prepare
from test_obs_tesseract import Engine,binary,recognize_top
from dual_source import recognize_side
from source_selection import select_source


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path)
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR' if os.name=='nt' else '/usr/share/tesseract-ocr/5')
    args=p.parse_args();expected=[(215,120)]*4+[(111,75)]*3+[(111,49),(101,58)]+[(103,61)]*5+[(103,64)]
    errors=[];comparisons=0;os.environ['OMP_THREAD_LIMIT']='2';cv2.setNumThreads(1);engine=Engine(args.directory)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with zipfile.ZipFile(args.archive) as archive:archive.extractall(root)
            if [c.name for c in sorted(root.glob('case_*'))]!=[f'case_{i:03d}' for i in range(15)]:raise ValueError('Expected the 15-case 20261010_224456 conflict archive')
            for i,(hp,mp) in enumerate(expected):
                folder=root/f'case_{i:03d}';meta=json.loads((folder/'reading.json').read_text());full=cv2.imread(str(folder/'full_frame.png'))
                for key,names in [('top_rectangles',['hp_top_original','mp_top_original']),('side_rectangles',['hp_side_original','mp_side_original']),('side_bar_rectangles',['hp_side_bar','mp_side_bar'])]:
                    for rect,name in zip(meta[key],names):
                        x,y,w,h=rect;native=cv2.imread(str(folder/(name+'.png')))
                        if not np.array_equal(full[y:y+h,x:x+w],native):errors.append([i,name,'different_frame_crop'])
                        comparisons+=1
                for k,(r,current,maximum) in enumerate([('hp',hp,215),('mp',mp,120)]):
                    crop=cv2.imread(str(folder/(r+'_top_original.png')))
                    top=recognize_top(engine,binary(prepare(crop,'dynamic')),True,raw_crop=crop,resource=r)
                    side=recognize_side(engine,cv2.imread(str(folder/(r+'_side_original.png'))),True)
                    evidence=meta['analysis']['readings'][k]['fill']
                    selected=select_source(top,side,evidence,maximum)
                    if (selected.get('value') or {}).get('current')!=current:errors.append([i,r,'wrong_or_missing_current',selected])
                    if i in (4,5,6,7) and r=='hp' and (top.get('value') or {}).get('current')!=111:errors.append([i,r,'top_111_not_recovered'])
                    if i==4 and r=='hp':
                        fallback=select_source(top,{'current':None,'reason':'layout_or_occlusion'},evidence,maximum)
                        if (fallback.get('value') or {}).get('current')!=111:errors.append([i,r,'top_unavailable_when_side_geometry_fails'])
                    if i==14 and r=='hp' and side.get('reason')!='foreign_color_overlay':errors.append([i,r,'thin_side_item_not_detected'])
    finally:engine.tess.close()
    report={'passed':not errors,'independently_labeled_resources':30,'same_frame_comparisons':comparisons,'errors':errors,
            'note':'Fresh top/side OCR against visually read native crops. Saved native fill measurements reused; no temporal replay or live observation log audit.'}
    print(json.dumps(report));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
