"""Disjoint native training/test frames; separate 15-case native validation."""
import argparse,hashlib,json,time,os
from pathlib import Path
import cv2
from template_counter import TemplateCounter,build_model
from text_occlusion import inspect_top_text

def labels(ref):
    result={}
    for r in ('hp','mp'):
        values=[]
        for start,end,current,maximum in ref[r]:
            if start!=len(values):raise ValueError('Noncontiguous labels')
            values.extend([current]*(end-start+1))
        result[r]=values
    return result

def valid_crop(crop,source,r):
    if source=='top':return not inspect_top_text(crop,r)['occluded']
    low=crop.min(axis=2).astype('int16');high=crop.max(axis=2).astype('int16')
    return int(((high-low>20)&(high>30)).sum())<max(4,crop.shape[0]*crop.shape[1]*.01)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('--reference',type=Path,default=Path(__file__).with_name('long_native_labels.json'));p.add_argument('--train-frames',type=int,default=2000);p.add_argument('--output',type=Path,default=Path('template_benchmark'));p.add_argument('--conflicts',type=Path);p.add_argument('--compare-ocr',action='store_true');p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR' if os.name=='nt' else '/usr/share/tesseract-ocr/5');p.add_argument('--model',type=Path)
    a=p.parse_args();cv2.setNumThreads(1);ref=json.loads(a.reference.read_text());truth=labels(ref);folders=sorted(a.dataset.glob('case_*'))
    if len(folders)!=ref['frames']:raise ValueError('Dataset frame count mismatch')
    if not 0<a.train_frames<len(folders):raise ValueError('Training/test must be disjoint')
    training=[]
    for i,folder in enumerate([] if a.model else folders[:a.train_frames]):
        for r in ('hp','mp'):
            current=truth[r][i]
            if current is None:continue
            for s in ('top','side'):
                crop=cv2.imread(str(folder/(r+'_'+s+'_original.png')))
                if valid_crop(crop,s,r):training.append((crop,s,current))
    model=json.loads(a.model.read_text()) if a.model else build_model(training)
    if a.model and (model.get('training_frame_range')!=[0,a.train_frames-1] or model.get('label_reference_sha256')!=hashlib.sha256(json.dumps(ref,sort_keys=True,separators=(',',':')).encode()).hexdigest()):raise ValueError('Frozen model split/reference mismatch')
    model['training_frame_range']=[0,a.train_frames-1];model['label_reference_sha256']=hashlib.sha256(json.dumps(ref,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    a.output.mkdir(parents=True,exist_ok=True);(a.output/'templates.json').write_text(json.dumps(model));reader=TemplateCounter(model);metrics={s:{'accepted':0,'correct':0,'wrong':0,'unavailable':0,'occluded':0} for s in ('top','side')};errors=[];pairs={'correct':0,'wrong':0,'missing':0,'conflict':0};times=[];matched={}
    baseline={s:{'correct':0,'wrong':0,'unavailable':0,'occluded':0} for s in ('top','side')};ocr_times=[];engine=None
    if a.compare_ocr:
        from test_obs_tesseract import Engine,binary,recognize_top
        from benchmark_hp_mp import prepare
        from dual_source import recognize_side
        engine=Engine(a.directory)
    def evaluate(folder,expected,scope):
        for r,current in expected.items():
            if current is None:continue
            values=[]
            for s in ('top','side'):
                crop=cv2.imread(str(folder/(r+'_'+s+'_original.png')))
                if not valid_crop(crop,s,r):
                    metrics[s]['occluded']+=1;baseline[s]['occluded']+=1;continue
                if engine is not None:
                    start=time.perf_counter()
                    old=recognize_top(engine,binary(prepare(crop,'dynamic')),True,raw_crop=crop,resource=r) if s=='top' else recognize_side(engine,crop,True)
                    ocr_times.append((time.perf_counter()-start)*1000)
                    old_current=(old.get('value') or {}).get('current') if s=='top' else old.get('current')
                    baseline[s]['unavailable' if old_current is None else 'correct' if old_current==current else 'wrong']+=1
                t=time.perf_counter();out=reader.read(crop,s);times.append((time.perf_counter()-t)*1000);value=out['current'];matched.setdefault(scope,{})[folder.name+':'+r+':'+s]=out
                if value is None:metrics[s]['unavailable']+=1;continue
                metrics[s]['accepted']+=1;metrics[s]['correct' if value==current else 'wrong']+=1;values.append(value)
                if value!=current and len(errors)<40:errors.append({'scope':scope,'case':folder.name,'resource':r,'source':s,'expected':current,'actual':out})
            unique=set(values)
            if not unique:pairs['missing']+=1
            elif len(unique)>1:pairs['conflict']+=1
            elif next(iter(unique))==current:pairs['correct']+=1
            else:pairs['wrong']+=1
    for i,folder in enumerate(folders[a.train_frames:],a.train_frames):evaluate(folder,{r:truth[r][i] for r in ('hp','mp')},'held_out_recording')
    if a.conflicts:
        expected=[(215,120)]*4+[(111,75)]*3+[(111,49),(101,58)]+[(103,61)]*5+[(103,64)]
        for i,v in enumerate(expected):evaluate(a.conflicts/f'case_{i:03d}',dict(zip(('hp','mp'),v)),'separate_recording')
    if engine is not None:engine.tess.close()
    times.sort();report={'training_frames':a.train_frames,'held_out_frames':len(folders)-a.train_frames,'sources':metrics,'available_pair_currents':pairs,'read_ms':{'median':times[len(times)//2],'p95':times[int(len(times)*.95)]},'errors':errors,'production_changed':False,'note':'Experimental current counters. Disjoint training/test frames. Candidates only, no production arbitration/confirmation. No OBS/actions.'}
    if a.compare_ocr:
        ocr_times.sort();report['ocr_baseline']={'sources':baseline,'median_counter_ms':ocr_times[len(ocr_times)//2],'p95_counter_ms':ocr_times[int(len(ocr_times)*.95)]}
    report['separate_recording']={s:{'total':15*2,'accepted':sum(v['current'] is not None for k,v in matched.get('separate_recording',{}).items() if k.endswith(':'+s))} for s in ('top','side')}
    report['candidate_coverage_passed']=pairs['missing']==0 and pairs['wrong']==0
    report['safe_to_replace_production']=False
    (a.output/'candidates.json').write_text(json.dumps(matched))
    (a.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));return 0
if __name__=='__main__':raise SystemExit(main())
