"""Measure response on labeled recorded frames, without OBS or OCR rerun."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import tempfile
import zipfile
from check_native_threshold_replay import labels


def distribution(values):
    values=sorted(values)
    return {'count':len(values),'median_ms':round(statistics.median(values),2),
            'p95_ms':round(values[min(len(values)-1,int((len(values)-1)*.95+.999))],2),
            'max_ms':round(values[-1],2)} if values else {'count':0}


def analyze(rows,reference,times):
    truth=labels(reference);n=reference['frames'];indexed={}
    for row in rows:
        if 'case' not in row:continue
        key=(row['case'],row['resource'])
        if key in indexed:raise ValueError('Duplicate replay sample')
        indexed[key]=row
    expected={(f'case_{i:05d}',r) for i in range(n) for r in ('hp','mp')}
    if set(indexed)!=expected or len(times)!=n:raise ValueError('Incomplete case coverage')
    if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Recorded times must increase')
    errors=[];resources={}
    for r in ('hp','mp'):
        available=[];selected=[];processing=[]
        for i in range(n):
            row=indexed[(f'case_{i:05d}',r)];want=truth[r][i][0]
            for kind in ('selected','confirmed'):
                value=(row.get(kind) or {}).get('value')
                if value and ((want is None and kind=='confirmed') or (want is not None and value.get('current')!=want)):
                    errors.append({'case':row['case'],'resource':r,'kind':kind,'reason':'wrong_current'})
            selected.append(bool((row.get('selected') or {}).get('value')))
            available.append(bool((row.get('confirmed') or {}).get('value')))
            processing.append(float(row.get('ms',0)))
        transitions=[]
        starts=[i for i in range(1,n) if truth[r][i][0] is not None and truth[r][i-1][0] is not None
                and truth[r][i][0]!=truth[r][i-1][0]]
        for i in starts:
            end=i+1
            while end<n and truth[r][end][0]==truth[r][i][0]:end+=1
            confirmed=next((j for j in range(i,end) if available[j]),None)
            transitions.append({'case':f'case_{i:05d}','from':truth[r][i-1][0],
                'to':truth[r][i][0],'direction':'drop' if truth[r][i][0]<truth[r][i-1][0] else 'rise',
                'delay_recorded_ms':round((times[confirmed]-times[i])*1000,2) if confirmed is not None else None,
                'confirmed_case':f'case_{confirmed:05d}' if confirmed is not None else None,
                'changed_again_before_confirmation':confirmed is None and end<n})
        gaps=[];i=0
        while i<n:
            if available[i]:i+=1;continue
            start=i
            while i<n and not available[i]:i+=1
            gaps.append({'first_case':f'case_{start:05d}','samples':i-start,
                         'duration_recorded_ms':round((times[i]-times[start])*1000,2) if i<n else None,
                         'open_at_end':i==n,'startup':start==0})
        delays=[t['delay_recorded_ms'] for t in transitions if t['delay_recorded_ms'] is not None]
        resources[r]={'samples':n,'selected_samples':sum(selected),'confirmed_samples':sum(available),
            'transitions':len(transitions),'confirmation_delay':distribution(delays),
            'transitions_over_200ms':[t for t in transitions if t['delay_recorded_ms'] is not None and t['delay_recorded_ms']>200],
            'never_confirmed_before_next_change':[t for t in transitions if t['delay_recorded_ms'] is None],
            'availability_gaps':gaps,'closed_gap_duration':distribution([g['duration_recorded_ms'] for g in gaps if g['duration_recorded_ms'] is not None and not g['startup']]),
            'offline_processing_resource':distribution(processing),'transition_details':transitions}
    return {'passed':not errors,'errors':errors,'resources':resources,
            'note':'Delays start at the first recorded frame with a new independently labeled current. Sampling misses changes between frames. No game-to-camera latency, live window state, publishing, keys or action latency measured. Processing times belong to the supplied offline replay, not live execution. Open trailing gaps have unknown duration.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay',type=Path);p.add_argument('archive',type=Path)
    p.add_argument('--reference',type=Path,default=Path(__file__).with_name('item_outline_native_labels.json'))
    args=p.parse_args();reference=json.loads(args.reference.read_text(encoding='utf-8'))
    rows=[json.loads(l) for l in args.replay.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
    print(f"Pomiar reakcji offline: {reference['frames']} klatek. Bez gry, OBS i ponownego OCR.",flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        dataset=args.archive
        with zipfile.ZipFile(dataset) as z:
            nested=[name for name in z.namelist() if name.startswith('ocr_dataset_') and name.endswith('.zip')]
            if len(nested)>1:raise ValueError('Multiple datasets in archive')
            if nested:
                dataset=Path(tmp)/'dataset.zip'
                with z.open(nested[0]) as src,dataset.open('wb') as dst:
                    import shutil
                    shutil.copyfileobj(src,dst)
        digest=hashlib.sha256()
        with dataset.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=reference['dataset_sha256']:raise ValueError('Archive does not match independent labels')
        with zipfile.ZipFile(dataset) as z:
            cases=sorted(name for name in z.namelist() if name.endswith('/reading.json'))
            if [name.rsplit('/',1)[0] for name in cases]!=[f'case_{i:05d}' for i in range(reference['frames'])]:raise ValueError('Archive coverage mismatch')
            times=[json.loads(z.read(name))['elapsed_s'] for name in cases]
    report=analyze(rows,reference,times)
    out=args.replay.with_name('response_time_checks.json');out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    compact={r:{k:v for k,v in details.items() if k not in ['transition_details','availability_gaps','transitions_over_200ms','never_confirmed_before_next_change']} for r,details in report['resources'].items()}
    print(json.dumps({'passed':report['passed'],'errors':report['errors'],'resources':compact,'note':report['note']}));print('Wynik:',out.resolve())
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
