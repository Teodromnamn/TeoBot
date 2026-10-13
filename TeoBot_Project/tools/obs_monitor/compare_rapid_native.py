"""Compare frozen templates + resident Tesseract with local RapidOCR models.

Current candidates only. No maximum, arbitration, temporal gate, OBS or actions.
Manifest entries contain name, archive/directory, labels_csv/labels_json, start.
Unique rasters are inferred once; timing excludes startup, disk and duplicates.
"""
import os
os.environ['ORT_DISABLE_TELEMETRY']='1'
os.environ.setdefault('OMP_THREAD_LIMIT','2')
import argparse,csv,hashlib,json,re,time,zipfile
from collections import Counter
from pathlib import Path
from importlib.metadata import version
import cv2
import numpy as np
from template_counter import TemplateCounter,parts
from benchmark_template_counter import valid_crop,labels
from benchmark_hp_mp import prepare
from test_obs_tesseract import Engine,binary,recognize_top
from dual_source import recognize_side,side_image

def parse(text,source,mode):
    text=re.sub(r'\s+','',text)
    pattern=r'\(?([0-9]+)/[0-9]+(?:\(.*)?' if source=='top' and mode!='digits' else r'([0-9]+)'
    match=re.fullmatch(pattern,text)
    return int(match.group(1)) if match else None

def preprocess(crop,source,mode):
    if mode=='native':return cv2.resize(crop,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)
    if mode=='binary':return binary(prepare(crop,'dynamic')) if source=='top' else side_image(crop)
    gs=parts(crop,source)
    if not gs:return None
    h=max(g.shape[0] for g in gs);w=sum(g.shape[1] for g in gs)+3*(len(gs)-1)
    image=np.full((h+8,w+8),255,np.uint8);x=4
    for g in gs:image[4:4+g.shape[0],x:x+g.shape[1]]=g;x+=g.shape[1]+3
    return cv2.resize(image,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)

def timing(ts):
    return {'count':len(ts),'median_ms':float(np.median(ts)),'p95_ms':float(np.percentile(ts,95))} if ts else {'count':0}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path);p.add_argument('--output',type=Path,default=Path('rapid_comparison'));p.add_argument('--directory',default='/usr/share/tesseract-ocr/5');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);cv2.setNumThreads(1)
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    import rapidocr
    from rapidocr import RapidOCR,LangRec,OCRVersion,ModelType
    common={'Global.use_det':False,'Global.use_cls':False,'Global.text_score':0.,'Global.log_level':'error','EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':1}
    models=Path(rapidocr.__file__).parent/'models';v6=models/'PP-OCRv6_rec_small.onnx';v5=models/'en_PP-OCRv5_rec_mobile.onnx'
    if not v6.is_file() or not v5.is_file():raise FileNotFoundError('Preload the recognition models before running offline')
    engines={'v6':RapidOCR(params=dict(common,**{'Rec.model_path':str(v6)})),'v5_en':RapidOCR(params=dict(common,**{'Rec.model_path':str(v5),'Rec.lang_type':LangRec.EN,'Rec.model_type':ModelType.MOBILE,'Rec.ocr_version':OCRVersion.PPOCRV5}))}
    dummy=np.full((48,120,3),255,np.uint8);cv2.putText(dummy,'123',(3,34),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,0),2)
    for e in engines.values():e(dummy,use_det=False,use_cls=False,use_rec=True)
    tess=Engine(a.directory,cache_limit=0);model_file=Path(__file__).with_name('counter_templates_v1.json');templates=TemplateCounter(json.loads(model_file.read_text()))
    variants=['tesseract','hybrid_tesseract']+[p+n+'_'+m for n in engines for m in ('native','binary','digits') for p in ('','hybrid_')]
    cache={};times={};reports=[];total={v:Counter() for v in variants}
    def read(crop,s,r):
        key=(s,r,crop.shape,hashlib.sha256(crop.tobytes()).hexdigest())
        if key in cache:return cache[key]
        if not valid_crop(crop,s,r):
            out={'occluded':True,'values':{}};cache[key]=out;return out
        t=time.perf_counter();tpl=templates.read(crop,s)['current'];times.setdefault('template',[]).append((time.perf_counter()-t)*1000)
        t=time.perf_counter();o=recognize_top(tess,binary(prepare(crop,'dynamic')),True,raw_crop=crop,resource=r) if s=='top' else recognize_side(tess,crop,True)
        val=(o.get('value') or {}).get('current') if s=='top' else o.get('current');ms=(time.perf_counter()-t)*1000;times.setdefault('tesseract',[]).append(ms)
        if tpl is None:times.setdefault('fallback_tesseract',[]).append(ms)
        vals={'tesseract':val,'hybrid_tesseract':tpl if tpl is not None else val};raw={};count=len(parts(crop,s))
        for n,e in engines.items():
            for mode in ('native','binary','digits'):
                name=n+'_'+mode;t=time.perf_counter();image=preprocess(crop,s,mode)
                o=e(image,use_det=False,use_cls=False,use_rec=True) if image is not None else None
                text=''.join(o.txts or ()) if o is not None else '';v=parse(text,s,mode)
                if v is not None and (count==0 or len(str(v))!=count):v=None
                ms=(time.perf_counter()-t)*1000;times.setdefault(name,[]).append(ms)
                if tpl is None:times.setdefault('fallback_'+name,[]).append(ms)
                vals[name]=v;vals['hybrid_'+name]=tpl if tpl is not None else v
                raw[name]={'text':text,'scores':list(o.scores) if o is not None else []}
        out={'occluded':False,'template':tpl,'values':vals,'raw':raw};cache[key]=out;return out
    def report():
        result={'versions':{'rapidocr':version('rapidocr'),'onnxruntime':version('onnxruntime'),'tesseract':tess.tess.version,'opencv':cv2.__version__},'model_hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (model_file,v5,v6)},'resource_samples':sum(d['samples'] for d in reports),'unique_source_rasters':len(cache),'variants':{v:dict(c) for v,c in total.items()},'timings_unique_cold':{v:timing(ts) for v,ts in times.items()},'datasets':reports,'note':'Current candidates only, no final arbitration/maxima/confirmation/actions. Template training frames excluded in main native dataset. Identical crops/occlusion filter, visible-digit-count guard, Rapid confidence recorded without score rejection. Synthetic source conflicts may be intentional. Two CPU threads, warm resident models, Tesseract pixel cache disabled. Timings exclude IO and duplicates, not live latency.'}
        (a.output/'summary.json').write_text(json.dumps(result,indent=2))
    try:
        with (a.output/'candidates.jsonl').open('w') as log:
            for spec in json.loads(a.manifest.read_text()):
                stats={v:Counter() for v in variants};z=zipfile.ZipFile(spec['archive']) if 'archive' in spec else None
                if 'labels_json' in spec:
                    ref=json.loads(Path(spec['labels_json']).read_text());truth=labels(ref)
                    if z and hashlib.sha256(Path(spec['archive']).read_bytes()).hexdigest()!=ref['dataset_sha256']:raise ValueError('Dataset/reference hash mismatch')
                    rows=[dict(case=f'case_{i:05d}',**{r+'_current':truth[r][i] for r in ('hp','mp')}) for i in range(len(truth['hp']))]
                else:rows=list(csv.DictReader(Path(spec['labels_csv']).open(encoding='utf-8-sig')))
                print('DATASET',spec['name'],len(rows),'start',spec.get('start',0),flush=True);samples=0
                for row in rows[spec.get('start',0):]:
                    for r in ('hp','mp'):
                        expected=row[r+'_current']
                        if expected in (None,'','None','null','?'):continue
                        expected=int(expected);outs={}
                        for s in ('top','side'):
                            name=row['case']+'/'+r+'_'+s+'_original.png';data=z.read(name) if z else (Path(spec['directory'])/name).read_bytes()
                            if row.get(r+'_source_sha256') and row.get(r+'_label_source')==s+'_original' and hashlib.sha256(data).hexdigest()!=row[r+'_source_sha256']:raise ValueError('Label image hash mismatch')
                            crop=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                            if crop is None:raise ValueError('Unreadable image')
                            outs[s]=read(crop,s,r)
                        for v in variants:
                            available={o['values'].get(v) for o in outs.values()}-{None};c=stats[v];c['samples']+=1;c['correct_available' if expected in available else 'missing' if not available else 'wrong_only']+=1
                            if len(available)>1:c['conflict']+=1
                            for s,o in outs.items():
                                x=o['values'].get(v);c[s+('_occluded' if o['occluded'] else '_missing' if x is None else '_correct' if x==expected else '_wrong')]+=1
                        log.write(json.dumps(dict(dataset=spec['name'],case=row['case'],resource=r,expected=expected,sources=outs))+'\n');samples+=1
                if z:z.close()
                log.flush();reports.append({'name':spec['name'],'samples':samples,'variants':{v:dict(c) for v,c in stats.items()}})
                for v,c in stats.items():total[v].update(c)
                report();print(json.dumps({'finished':spec['name'],'samples':samples,'hybrid':stats['hybrid_tesseract']}),flush=True)
    finally:tess.tess.close()
    print('DONE',str(a.output/'summary.json'),flush=True)
if __name__=='__main__':main()
