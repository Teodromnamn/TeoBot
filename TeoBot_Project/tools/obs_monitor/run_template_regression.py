"""Inventory and test available offline crop archives with frozen templates.

Current candidates only; no production arbitration/maxima/actions. Wrong source
candidates can reflect occlusion or intentional synthetic source skew.
"""
import argparse,csv,hashlib,io,json,tempfile,zipfile,time
from pathlib import Path
import cv2
from template_counter import TemplateCounter
from benchmark_template_counter import valid_crop,labels

OLD_LABELS={
 'ocr_dataset_20261006_104102_660600.zip':'hp_mp_manual_audit.zip',
 'ocr_dataset_20261006_203712_874309.zip':'hp_mp_colored_manual_audit.zip',
 'ocr_dataset_20261008_185859_003221.zip':'hp_mp_latest_manual_audit.zip',
 'ocr_dataset_20261008_192013_656822.zip':'hp_mp_normal_manual_audit.zip'}

def csv_labels(text):
    result={}
    for row in csv.DictReader(io.StringIO(text)):
        if row['case'] in result:raise ValueError('Duplicate CSV label case')
        result[row['case']]=row
    return result

def current(value):
    return None if value in (None,'','null','None','?') else int(value)

def candidate_status(outputs,expected):
    if expected is None:return 'unlabeled',False
    values={o['current'] for o in outputs.values() if o['current'] is not None}
    status='candidate_correct_available' if expected in values else 'candidate_missing' if not values else 'only_wrong_candidates'
    return status,len(values)>1


def bundle_inputs(root,destination):
    """Expose nested synthetic datasets with their adjacent label CSVs."""
    for package in sorted(root.glob('hp_mp_*.zip')):
        if not zipfile.is_zipfile(package):continue
        with zipfile.ZipFile(package) as archive:
            for name in archive.namelist():
                path=Path(name)
                if path.name not in ('dataset.zip','synthetic_occlusion.zip'):continue
                target=destination/package.stem/path.parent.name
                target.mkdir(parents=True,exist_ok=True);(target/path.name).write_bytes(archive.read(name))
                for label in archive.namelist():
                    lp=Path(label)
                    if lp.parent==path.parent and lp.name.startswith('labels') and lp.suffix=='.csv':(target/lp.name).write_bytes(archive.read(label))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--output',type=Path,default=Path('template_regression'));a=p.parse_args();a.root=a.root.resolve();a.output.mkdir(parents=True,exist_ok=True);folder=Path(__file__).resolve().parent;model=json.loads((folder/'counter_templates_v1.json').read_text());reader=TemplateCounter(model);cv2.setNumThreads(1)
    refs={}
    for name in ['long_native_labels.json','occlusion_native_labels.json','item_outline_native_labels.json','counter_native_224456_labels.json']:
        path=folder/name
        if path.exists():
            ref=json.loads(path.read_text());refs[ref['dataset_sha256']]=(ref,name)
    bundle_inputs(a.root,a.output/'_bundle_inputs')
    archives=sorted(p for p in a.root.rglob('*.zip') if p.name.startswith(('ocr_dataset_','ocr_conflicts_','long_diagnostic_')) or p.name in ('dataset.zip','synthetic_occlusion.zip'))
    reports=[];skipped=[];seen=set();timings=[];unique=set();training_unique=set()
    with (a.output/'candidates.jsonl').open('w',encoding='utf-8') as log:
        for archive in archives:
            try:
                with zipfile.ZipFile(archive) as z:
                    nested=[n for n in z.namelist() if n.startswith('ocr_dataset_') and n.endswith('.zip')]
                    data=z.read(nested[0]) if nested else archive.read_bytes();name=Path(nested[0]).name if nested else archive.name
                digest=hashlib.sha256(data).hexdigest()
                if digest in seen:skipped.append({'archive':str(archive),'reason':'duplicate_dataset_hash'});continue
                reference=refs.get(digest);truth={};ref_name=None;kind='unlabeled';training=False
                if reference:
                    ref,ref_name=reference;cols=labels(ref);truth={f'case_{i:05d}':{r+'_current':cols[r][i] for r in ('hp','mp')} for i in range(ref['frames'])};kind='native_labeled';training=digest==model['training_dataset_sha256']
                elif name in OLD_LABELS:
                    label_archive=next(a.root.rglob(OLD_LABELS[name]),None)
                    if label_archive:
                        with zipfile.ZipFile(label_archive) as z:
                            n=next(n for n in z.namelist() if n.endswith('labels_current_manual.csv'));truth=csv_labels(z.read(n).decode('utf-8-sig'));ref_name=label_archive.name+':'+n;kind='native_labeled'
                elif name=='ocr_conflicts_20261010_224456_535478.zip':
                    expected=[(215,120)]*4+[(111,75)]*3+[(111,49),(101,58)]+[(103,61)]*5+[(103,64)]
                    truth={f'case_{i:03d}':dict(zip(('hp_current','mp_current'),v)) for i,v in enumerate(expected)};ref_name='independent_15_case_native_labels';kind='native_labeled'
                else:
                    label_files=sorted(archive.parent.glob('labels*.csv'))
                    if label_files:truth=csv_labels(label_files[0].read_text(encoding='utf-8-sig'));ref_name=str(label_files[0]);kind='synthetic_labeled'
                report={'archive':str(archive),'dataset_name':name,'dataset_sha256':digest,'kind':kind,'reference':ref_name,'frames':0,'test_labeled_currents':0,'training_currents':0,'unlabeled_currents':0,'candidate_correct_available':0,'candidate_missing':0,'candidate_conflicting':0,'only_wrong_candidates':0,'sources':{s:{'correct':0,'differs_reference':0,'unavailable':0,'occluded':0,'unlabeled_available':0} for s in ('top','side')},'examples':[]}
                print('Test:',name,kind,flush=True)
                with tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp)
                    with zipfile.ZipFile(io.BytesIO(data)) as z:z.extractall(root)
                    cases=sorted(root.glob('case_*'))
                    if truth and set(truth)!=set(c.name for c in cases):raise ValueError('Label/case coverage mismatch')
                    for index,case in enumerate(cases):
                        report['frames']+=1
                        for r in ('hp','mp'):
                            row=truth.get(case.name,{});expected=current(row.get(r+'_current'));is_training=training and index<=model['training_frame_range'][1];category='unlabeled_currents' if expected is None else 'training_currents' if is_training else 'test_labeled_currents';report[category]+=1;outs={};pixels=[]
                            for s in ('top','side'):
                                path=case/(r+'_'+s+'_original.png');crop=cv2.imread(str(path))
                                if crop is None:raise ValueError('Missing crop '+str(path))
                                pixels.append(crop.tobytes());source_hash=row.get(r+'_source_sha256');label_source=row.get(r+'_label_source')
                                if source_hash and label_source==s+'_original' and hashlib.sha256(path.read_bytes()).hexdigest()!=source_hash:raise ValueError('Manual crop hash mismatch '+str(path))
                                if not valid_crop(crop,s,r):outs[s]={'current':None,'reason':'occlusion_filter'};key='occluded'
                                else:
                                    start=time.perf_counter();out=reader.read(crop,s);timings.append((time.perf_counter()-start)*1000);outs[s]=out;v=out['current'];key='unavailable' if v is None else 'unlabeled_available' if expected is None else 'correct' if v==expected else 'differs_reference'
                                report['sources'][s][key]+=1
                                if key=='differs_reference' and len(report['examples'])<20:report['examples'].append({'case':case.name,'resource':r,'source':s,'expected':expected,'actual':outs[s]})
                            signature=hashlib.sha256(b''.join(pixels)).hexdigest()
                            (training_unique if is_training else unique).add(signature)
                            if expected is not None and not is_training:
                                status,conflict=candidate_status(outs,expected);report[status]+=1
                                if conflict:report['candidate_conflicting']+=1
                            log.write(json.dumps({'dataset':name,'dataset_sha256':digest,'archive':str(archive),'case':case.name,'resource':r,'expected_current':expected,'training':is_training,'outputs':outs})+'\n')
                seen.add(digest)
                reports.append(report);print(json.dumps({k:report[k] for k in ['frames','test_labeled_currents','candidate_correct_available','candidate_missing','candidate_conflicting','only_wrong_candidates']}),flush=True)
            except (zipfile.BadZipFile,ValueError,OSError,KeyError) as e:skipped.append({'archive':str(archive),'reason':str(e)})
    timings.sort();summary={'datasets':reports,'skipped':skipped,'model_sha256':hashlib.sha256((folder/'counter_templates_v1.json').read_bytes()).hexdigest(),'training_currents':sum(r['training_currents'] for r in reports),'test_labeled_currents':sum(r['test_labeled_currents'] for r in reports),'unlabeled_currents':sum(r['unlabeled_currents'] for r in reports),'correct_candidate_available':sum(r['candidate_correct_available'] for r in reports),'missing_candidates':sum(r['candidate_missing'] for r in reports),'only_wrong_candidates':sum(r['only_wrong_candidates'] for r in reports),'conflicting_candidates':sum(r['candidate_conflicting'] for r in reports),'unique_test_pixel_pairs':len(unique),'test_pixel_pairs_also_in_training':len(unique&training_unique),'median_counter_ms':timings[len(timings)//2] if timings else None,'note':'Raw CURRENT candidates only, not production selection/confirmation/maxima/actions. Training separated from test coverage. Synthetic source differences may be intentional skew. Unlabeled archives have no accuracy verdict; repeated pixel pairs reported.'}
    summary['fully_labeled_test_passed']=summary['test_labeled_currents']>0 and summary['missing_candidates']==0 and summary['only_wrong_candidates']==0
    summary['production_changed']=False
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k not in ('datasets','skipped')}));print('Report:',str((a.output/'summary.json').resolve()));return 0 if summary['fully_labeled_test_passed'] else 1
if __name__=='__main__':raise SystemExit(main())
