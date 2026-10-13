"""Offline observation decisions using production publication and recorded times."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import zipfile
from check_native_threshold_replay import PublicationCollector,labels
from check_native_response_time import analyze
from observation_policy import ObservationPolicy
import test_obs_pipeline as pipeline


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('replay',type=Path);p.add_argument('archive',type=Path)
    p.add_argument('--reference',type=Path,default=Path(__file__).with_name('item_outline_native_labels.json'))
    p.add_argument('--hp-threshold',type=float,default=100);p.add_argument('--mp-threshold',type=float,default=100)
    p.add_argument('--threshold-unit',choices=['current','percent'],default='current')
    p.add_argument('--cooldown-ms',type=float,default=1000)
    args=p.parse_args();policy=ObservationPolicy(args.hp_threshold,args.mp_threshold,args.threshold_unit,args.cooldown_ms)
    ref=json.loads(args.reference.read_text(encoding='utf-8'));truth=labels(ref)
    rows=[json.loads(line) for line in args.replay.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    with tempfile.TemporaryDirectory() as tmp:
        dataset=args.archive
        with zipfile.ZipFile(dataset) as z:
            nested=[name for name in z.namelist() if name.startswith('ocr_dataset_') and name.endswith('.zip')]
            if len(nested)>1:raise ValueError('Multiple datasets')
            if nested:
                dataset=Path(tmp)/'dataset.zip'
                with z.open(nested[0]) as src,dataset.open('wb') as dst:
                    import shutil
                    shutil.copyfileobj(src,dst)
        digest=hashlib.sha256()
        with dataset.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=ref['dataset_sha256']:raise ValueError('Wrong dataset for labels')
        with zipfile.ZipFile(dataset) as z:
            names=sorted(n for n in z.namelist() if n.endswith('/reading.json'))
            if [n.rsplit('/',1)[0] for n in names]!=[f'case_{i:05d}' for i in range(ref['frames'])]:raise ValueError('Archive coverage mismatch')
            times=[json.loads(z.read(name))['elapsed_s'] for name in names]
        validity=analyze(rows,ref,times)
        if not validity['passed']:raise ValueError('Replay contains incorrect labeled values')
        indexed={(r['case'],r['resource']):r for r in rows if 'case' in r}
        collector=PublicationCollector(Path(tmp)/'latest.json');previous=pipeline._result_publisher;errors=[];last={};count=0
        output=args.replay.with_name('observation_decisions.jsonl')
        print(f"Obserwacja offline: {ref['frames']} klatek. Bez OCR, gry, OBS i klawiszy.",flush=True)
        try:
            pipeline._result_publisher=collector
            with output.open('w',encoding='utf-8') as f:
                for i,t in enumerate(times):
                    case=f'case_{i:05d}';readings=[indexed[(case,r)]['confirmed'] for r in ('hp','mp')]
                    statuses=['bounded_conflict' if r.get('confirmed_range') else 'side_only' if r.get('value') and r['value'].get('maximum') is None else 'ok' if r.get('value') else 'unreadable' for r in readings]
                    mono=(t-times[0])*1000;wall=1_000_000+mono
                    with patch.object(pipeline.time,'time_ns',return_value=int(wall*1_000_000)):
                        pipeline.publish(collector.path,'BRAK_ODCZYTU',readings,0,5000,statuses)
                    decisions=policy.evaluate(collector.data,wall,mono)
                    for r,d in decisions.items():
                        count+=1
                        if d['decision']!='would_execute':continue
                        current=truth[r][i][0];res=collector.data['resources'][r];maximum=res.get('effective_maximum')
                        oracle=current if policy.unit=='current' else 100*current/maximum if current is not None and maximum else None
                        if oracle is None or oracle>=policy.thresholds[r]:errors.append([case,r,'incorrect_would_execute'])
                        if r in last and mono-last[r]<policy.cooldown_ms:errors.append([case,r,'cooldown_violated'])
                        last[r]=mono
                    f.write(json.dumps({'case':case,'elapsed_ms':round(mono,3),'mode':'observation_only','decisions':decisions})+'\n')
        finally:pipeline._result_publisher=previous
    report={**policy.summary(),'passed':not errors,'errors':errors,'frames':ref['frames'],'decision_checks':count,
            'note':'Production publication and read-only policy on independent native labels. Recorded sample clock, zero simulated camera age. No OCR rerun, live window events, keys or game feedback. Simulated actions do not change recorded HP/MP. Percentage rules use accepted cached maximum.'}
    result=args.replay.with_name('observation_checks.json');result.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));print('Wyniki:',result.resolve(),output.resolve())
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
