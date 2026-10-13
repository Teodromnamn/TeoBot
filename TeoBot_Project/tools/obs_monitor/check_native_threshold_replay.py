"""Offline decision audit of an already labeled native replay; no OCR or inputs.

Uses production publish() and below_threshold(). Checks absolute thresholds
against independent visual labels. Percentage checks distinguish cached-maximum
policy from the actual maximum visible in the reference images.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from check_long_native_audit import evaluate
from threshold_decision import below_threshold
import test_obs_pipeline as pipeline


class PublicationCollector:
    """Collect production publication payloads without disk or background threads."""
    def __init__(self,path): self.path=path; self.data={}
    def snapshot(self): return deepcopy(self.data)
    def submit(self,data): self.data=deepcopy(data)


def labels(reference):
    result={}
    for resource in ('hp','mp'):
        values=[]
        for start,end,current,maximum in reference[resource]:
            if start!=len(values) or end<start: raise ValueError('Invalid independent label runs')
            values.extend([(current,maximum)]*(end-start+1))
        if len(values)!=reference['frames']: raise ValueError('Wrong independent label count')
        result[resource]=values
    return result


def audit(rows,reference):
    truth=labels(reference)
    indexed={}
    for row in rows:
        if 'case' not in row: continue
        key=(row['case'],row['resource'])
        if key in indexed: raise ValueError('Duplicate replay row: '+str(key))
        indexed[key]=row
    expected={(f'case_{i:05d}',r) for i in range(reference['frames']) for r in ('hp','mp')}
    if set(indexed)!=expected: raise ValueError('Replay case coverage does not match independent labels')
    rules={r:[('current',n) for n in ([20,50,100,150] if r=='hp' else [5,10,25,50])]+
             [('percent',n) for n in (10,25,50,75)] for r in ('hp','mp')}
    counts={f'{r}:{unit}<{n}':Counter() for r in rules for unit,n in rules[r]}
    errors=[]; cached_differences=[]; checked=0; expiry_checks=0
    with tempfile.TemporaryDirectory() as tmp:
        collector=PublicationCollector(Path(tmp)/'latest.json')
        old= pipeline._result_publisher
        pipeline._result_publisher=collector
        try:
            for i in range(reference['frames']):
                case=f'case_{i:05d}'
                readings=[indexed[(case,r)].get('confirmed') or {} for r in ('hp','mp')]
                statuses=['bounded_conflict' if r.get('confirmed_range') else
                          ('side_only' if r.get('value') and r['value'].get('maximum') is None else
                           'ok' if r.get('value') else 'unreadable') for r in readings]
                now=1_000_000+i*100  # Synthetic publication clock; not live latency.
                with patch.object(pipeline.time,'time_ns',return_value=now*1_000_000):
                    pipeline.publish(collector.path,'BRAK_ODCZYTU',readings,0,5000,statuses)
                for resource in ('hp','mp'):
                    published=collector.data['resources'][resource]
                    current,maximum=truth[resource][i]
                    for unit,threshold in rules[resource]:
                        stats=counts[f'{resource}:{unit}<{threshold}']
                        decision=below_threshold(published,threshold,unit,now)['decision']
                        stats[decision]+=1;checked+=1
                        if current is None:
                            stats['ambiguous_reference']+=1
                            if decision!='unavailable': errors.append([case,resource,unit,threshold,'ambiguous_available'])
                            continue
                        if decision=='unavailable':
                            if readings[0 if resource=='hp' else 1].get('value') is not None:
                                errors.append([case,resource,unit,threshold,'confirmed_value_unavailable'])
                            stats['unconfirmed_or_missing']+=1
                            continue
                        # Cached maximum is explicitly allowed by the user's policy.
                        effective=published['effective_maximum']
                        oracle=current if unit=='current' else (100*current/effective if effective else None)
                        if oracle is None:
                            errors.append([case,resource,unit,threshold,'no_effective_maximum']);continue
                        wanted='execute' if oracle<threshold else 'do_not_execute'
                        if decision!=wanted:
                            stats['wrong_decisions']+=1
                            errors.append([case,resource,unit,threshold,decision,wanted])
                        else: stats['correct_decisions']+=1
                        if unit=='percent':
                            visible_wanted='execute' if 100*current/maximum<threshold else 'do_not_execute'
                            if wanted!=visible_wanted:
                                stats['cached_maximum_threshold_difference']+=1
                                cached_differences.append({'case':case,'resource':resource,'threshold_percent':threshold,
                                    'current':current,'cached_maximum':effective,'visible_maximum':maximum,
                                    'decision':wanted,'with_visible_maximum':visible_wanted})
                        expired=below_threshold(published,threshold,unit,now+5001)['decision']
                        expiry_checks+=1
                        if expired!='unavailable': errors.append([case,resource,'expired_available'])
        finally: pipeline._result_publisher=old
    return {'passed':not errors,'frames':reference['frames'],'decision_checks':checked,
            'expiry_checks':expiry_checks,'errors':errors,'cached_maximum_differences':cached_differences,'rules':{k:dict(v) for k,v in counts.items()},
            'note':'Production publishing and threshold evaluation with independent visual labels. '
            'Synthetic publication clock; no OBS, OCR rerun, keys, cooldowns or action latency. '
            'Unconfirmed frames stay unavailable. Percentage decisions use last known maximum; '
            'differences from visible maximum are reported separately.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay',type=Path)
    p.add_argument('--output',type=Path,default=Path('long_native_audit/threshold_checks.json'))
    args=p.parse_args()
    rows=[json.loads(line) for line in args.replay.read_text(encoding='utf-8').splitlines() if line.strip()]
    validated=evaluate(rows)
    if not validated['passed']: raise SystemExit('Native labeled audit failed: '+json.dumps(validated['errors']))
    reference=json.loads(Path(__file__).with_name('long_native_labels.json').read_text(encoding='utf-8'))
    print('Test decyzji offline: 5281 klatek. Bez gry, OBS i naciskania klawiszy.',flush=True)
    result=audit(rows,reference)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));print('Wynik: '+str(args.output.resolve()))
    if not result['passed']: raise SystemExit(1)

if __name__=='__main__': main()
