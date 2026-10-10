"""Audit the complete 20261010_200322 native recording offline.

Labels were read from original images grouped by identical text masks/crops.
One visually inconsistent HP frame deliberately has no exact current label.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def evaluate(rows):
    summary=rows[-1].get('summary',{}) if rows else {}
    errors=[]
    required={'resource_samples':10562,'manually_labeled':10561,'labeled_selected':10561}
    for key,expected in required.items():
        if summary.get(key)!=expected:errors.append({'counter':key,'expected':expected,'actual':summary.get(key)})
    for key in ['wrong_labeled_selected_current','wrong_labeled_confirmed_current','wrong_labeled_confirmed_maximum']:
        if summary.get(key)!=0:errors.append({'counter':key,'actual':summary.get(key)})
    ambiguous=[r for r in rows if r.get('case')=='case_01340' and r.get('resource')=='hp']
    if len(ambiguous)!=1 or (ambiguous[0].get('confirmed') or {}).get('value') is not None:
        errors.append({'case':'case_01340','resource':'hp','reason':'ambiguous_frame_confirmed_or_missing'})
    return {'passed':not errors,'errors':errors,'independently_labeled':summary.get('manually_labeled'),
            'correct_selected':summary.get('labeled_selected',0)-summary.get('wrong_labeled_selected_current',0),
            'confirmed_labeled':summary.get('labeled_confirmed'),
            'ambiguous_resources':1,'note':'Entire native recording. One HP frame shows top 144 and side 130: no unique ground truth; confirmation must remain unavailable.'}


def write_labels(path,reference):
    columns={}
    for resource in ('hp','mp'):
        values=[]
        for start,end,current,maximum in reference[resource]:
            if start!=len(values) or end<start:
                raise ValueError('Manual label runs have a gap or overlap')
            values.extend([(current,maximum)]*(end-start+1))
        if len(values)!=reference['frames']:raise ValueError('Manual label count mismatch')
        columns[resource]=values
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f)
        writer.writerow(['case','hp_current','hp_maximum','mp_current','mp_maximum'])
        for i,(hp,mp) in enumerate(zip(columns['hp'],columns['mp'])):
            writer.writerow([f'case_{i:05d}',*hp,*mp])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path)
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR' if os.name=='nt' else '/usr/share/tesseract-ocr/5')
    p.add_argument('--output',type=Path,default=Path('long_native_audit'))
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    folder=Path(__file__).resolve().parent
    reference=json.loads((folder/'long_native_labels.json').read_text(encoding='utf-8'))
    print('Pelny audyt offline: 5281 klatek / 10562 wartosci. Gra i OBS nie sa potrzebne.',flush=True)
    output=args.output/'replay_labeled.jsonl'
    with tempfile.TemporaryDirectory() as tmp:
        dataset=args.archive
        with zipfile.ZipFile(dataset) as z:
            nested=[n for n in z.namelist() if n.startswith('ocr_dataset_') and n.endswith('.zip')]
            if nested:
                dataset=Path(tmp)/'dataset.zip'
                with z.open(nested[0]) as src,dataset.open('wb') as dst:
                    import shutil
                    shutil.copyfileobj(src,dst)
        digest=hashlib.sha256()
        with dataset.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=reference['dataset_sha256']:
            raise SystemExit('To nie jest dataset odpowiadajacy recznym etykietom tego audytu.')
        labels=Path(tmp)/'labels.csv'
        write_labels(labels,reference)
        command=[sys.executable,'-X','utf8',str(folder/'replay_hp_mp_dataset.py'),str(dataset),
                 '--resilient-verification','--labels',str(labels),
                 '--directory',args.directory]
        with output.open('w',encoding='utf-8') as f:
            result=subprocess.run(command,stdout=f)
    if result.returncode:raise SystemExit(result.returncode)
    rows=[json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    report=evaluate(rows)
    (args.output/'audit_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));print(f'Wyniki: {args.output.resolve()}',flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
