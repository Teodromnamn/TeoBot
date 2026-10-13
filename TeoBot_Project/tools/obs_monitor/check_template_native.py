"""Frozen-template native comparison. Offline; does not modify live OCR."""
import argparse,json,tempfile,zipfile,time
from pathlib import Path
import cv2
from template_counter import TemplateCounter
from benchmark_template_counter import valid_crop

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);a=p.parse_args()
    reader=TemplateCounter(json.loads(Path(__file__).with_name('counter_templates_v1.json').read_text()))
    expected=[(215,120)]*4+[(111,75)]*3+[(111,49),(101,58)]+[(103,61)]*5+[(103,64)]
    errors=[];sources={s:{'correct':0,'wrong':0,'unavailable':0,'occluded':0} for s in ('top','side')};available=0;timings=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        with zipfile.ZipFile(a.archive) as z:z.extractall(root)
        if [p.name for p in sorted(root.glob('case_*'))]!=[f'case_{i:03d}' for i in range(15)]:raise ValueError('Expected 15-case 20261010_224456 archive')
        for i,(hp,mp) in enumerate(expected):
            for r,truth in [('hp',hp),('mp',mp)]:
                correct=False
                for s in ('top','side'):
                    crop=cv2.imread(str(root/f'case_{i:03d}'/(r+'_'+s+'_original.png')))
                    if not valid_crop(crop,s,r):sources[s]['occluded']+=1;continue
                    start=time.perf_counter();out=reader.read(crop,s);timings.append((time.perf_counter()-start)*1000)
                    value=out['current'];key='unavailable' if value is None else 'correct' if value==truth else 'wrong';sources[s][key]+=1
                    correct|=value==truth
                    if key=='wrong':errors.append({'case':i,'resource':r,'source':s,'expected':truth,'actual':out})
                if correct:available+=1
                else:errors.append({'case':i,'resource':r,'reason':'no_correct_candidate'})
    timings.sort();report={'passed':not errors,'independently_labeled_currents':30,'correct_candidate_available':available,'sources':sources,'errors':errors,'median_counter_ms':timings[len(timings)//2],'note':'Frozen font templates trained on earlier recording. Current values only; no maximum, production arbitration, confirmation, OBS or actions tested.'}
    print(json.dumps(report));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
