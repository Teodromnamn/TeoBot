"""Offline cooldown simulation. Never sends input or changes the live monitor.

Test assumptions: below-threshold is a level condition, successful simulated
requests start cooldown, and another request needs a newer observation. A
failed request does not start cooldown. Timing is supplied by the test/recording.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from check_long_native_audit import evaluate
from threshold_decision import below_threshold


class CooldownSimulation:
    def __init__(self,threshold,cooldown_ms,unit='current'):
        self.threshold=threshold;self.cooldown_ms=cooldown_ms;self.unit=unit
        self.last_success=None;self.last_observation=None

    def step(self,resource,observation,wall_ms,monotonic_ms,dispatch_success=True):
        decision=below_threshold(resource,self.threshold,self.unit,wall_ms)['decision']
        if decision!='execute': return decision
        if self.last_observation is not None and observation<=self.last_observation:
            return 'repeated_observation'
        if self.last_success is not None and monotonic_ms-self.last_success<self.cooldown_ms:
            return 'cooldown'
        if not dispatch_success: return 'simulated_send_failed'
        self.last_success=monotonic_ms;self.last_observation=observation
        return 'simulated_action'


def resource(current,observed=0,maximum=100,confirmed=True):
    return {'valid':confirmed,'value':{'current':current,'maximum':maximum} if confirmed else None,
            'observed_at_unix_ms':observed,'expires_at_unix_ms':observed+5000,
            'effective_percent':100*current/maximum}


class Tests(unittest.TestCase):
    def test_low_hp_repeats_only_after_cooldown_with_new_frame(self):
        gate=CooldownSimulation(10,1000)
        self.assertEqual(gate.step(resource(5),1,0,0),'simulated_action')
        self.assertEqual(gate.step(resource(5,100),2,100,100),'cooldown')
        self.assertEqual(gate.step(resource(5,1000),3,1000,1000),'simulated_action')

    def test_same_frame_never_retriggers_even_after_cooldown(self):
        gate=CooldownSimulation(10,1000)
        gate.step(resource(5),1,0,0)
        self.assertEqual(gate.step(resource(5),1,2000,2000),'repeated_observation')
        self.assertEqual(gate.step(resource(5),0,2000,2000),'repeated_observation')

    def test_exact_boundary_not_below(self):
        self.assertEqual(CooldownSimulation(10,1000).step(resource(10),1,0,0),'do_not_execute')

    def test_healed_value_blocks_and_later_drop_can_trigger(self):
        gate=CooldownSimulation(10,1000)
        gate.step(resource(5),1,0,0)
        self.assertEqual(gate.step(resource(30,2000),2,2000,2000),'do_not_execute')
        self.assertEqual(gate.step(resource(5,2100),3,2100,2100),'simulated_action')

    def test_failed_send_does_not_consume_cooldown_or_observation(self):
        gate=CooldownSimulation(10,1000)
        self.assertEqual(gate.step(resource(5),1,0,0,False),'simulated_send_failed')
        self.assertEqual(gate.step(resource(5),1,100,100),'simulated_action')

    def test_unconfirmed_and_expired_block(self):
        gate=CooldownSimulation(10,1000)
        self.assertEqual(gate.step(resource(5,confirmed=False),1,0,0),'unavailable')
        self.assertEqual(gate.step(resource(5),2,5001,5001),'unavailable')

    def test_400ms_allowed(self):
        self.assertEqual(CooldownSimulation(10,1000).step(resource(5),1,400,400),'simulated_action')

    def test_disappearance_and_restore_keep_cooldown(self):
        gate=CooldownSimulation(10,1000)
        gate.step(resource(5),1,0,0)
        self.assertEqual(gate.step({'valid':False},2,100,100),'unavailable')
        self.assertEqual(gate.step(resource(5,200),3,200,200),'cooldown')
        self.assertEqual(gate.step(resource(5,1100),4,1100,1100),'simulated_action')

    def test_clock_jump_does_not_release_cooldown(self):
        gate=CooldownSimulation(10,1000)
        gate.step(resource(5),1,0,0)
        self.assertEqual(gate.step(resource(5,100000),2,100000,100),'cooldown')

    def test_interval_below_threshold_allowed_straddling_blocked(self):
        gate=CooldownSimulation(10,1000)
        r={'range_valid':True,'value_range':{'lower':5,'upper':6},'expires_at_unix_ms':5000}
        self.assertEqual(gate.step(r,1,0,0),'simulated_action')
        r['value_range']={'lower':5,'upper':11}
        self.assertEqual(gate.step(r,2,2000,2000),'uncertain')

    def test_hp_and_mp_cooldowns_are_independent_in_this_simulation(self):
        hp=CooldownSimulation(10,1000);mp=CooldownSimulation(10,1000)
        self.assertEqual(hp.step(resource(5),1,0,0),'simulated_action')
        self.assertEqual(mp.step(resource(5),1,0,0),'simulated_action')


def native_replay(rows,reference,dataset):
    truth={r:[(current,maximum) for start,end,current,maximum in reference[r]
              for _ in range(start,end+1)] for r in ('hp','mp')}
    if any(len(v)!=reference['frames'] for v in truth.values()): raise ValueError('Wrong label count')
    indexed={(r['case'],r['resource']):r for r in rows if 'case' in r}
    policies=[(r,threshold,cooldown) for r,threshold in [('hp',50),('hp',100),('mp',10),('mp',25)]
              for cooldown in (500,1000,2000)]
    gates={key:CooldownSimulation(key[1],key[2]) for key in policies}
    counts={key:Counter() for key in policies};last={};errors=[];previous_time=-1
    with zipfile.ZipFile(dataset) as z:
        for i in range(reference['frames']):
            case=f'case_{i:05d}'
            meta=json.loads(z.read(case+'/reading.json'))
            elapsed=meta['elapsed_s']*1000
            if elapsed<previous_time: raise ValueError('Recording times are not ordered')
            previous_time=elapsed
            for name,threshold,cooldown in policies:
                confirmed=indexed[(case,name)].get('confirmed') or {}
                value=confirmed.get('value')
                # No live camera age in replay: publication age is zero here.
                r={'valid':value is not None,'value':value,'expires_at_unix_ms':elapsed+5000}
                gate=gates[(name,threshold,cooldown)]
                decision=gate.step(r,i,elapsed,elapsed)
                counts[(name,threshold,cooldown)][decision]+=1
                if decision!='simulated_action': continue
                key=(name,threshold,cooldown)
                expected_current=truth[name][i][0]
                if expected_current is None or expected_current>=threshold:
                    errors.append([case,list(key),'false_simulated_action',expected_current])
                if key in last and elapsed-last[key]<cooldown:
                    errors.append([case,list(key),'cooldown_violation'])
                last[key]=elapsed
    return {'passed':not errors,'frames':reference['frames'],'policy_checks':reference['frames']*len(policies),
        'errors':errors,'policies':[{ 'resource':r,'threshold_current':t,'cooldown_ms':c,
                                    **dict(counts[(r,t,c)])} for r,t,c in policies],
        'note':'Open-loop offline simulation on recorded sample times. Successful requests are simulated; '
               'they do not change recorded HP/MP. Test cooldowns are assumptions, not measured game cooldowns. '
               'No keys, shared cooldown groups, game confirmation, camera age or action latency simulated.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay',type=Path,nargs='?');p.add_argument('archive',type=Path,nargs='?')
    p.add_argument('--output',type=Path,default=Path('long_native_audit/cooldown_checks.json'))
    args=p.parse_args()
    if bool(args.replay)!=bool(args.archive): p.error('Supply both replay and diagnostic/dataset ZIP, or neither')
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not tests.wasSuccessful(): raise SystemExit(1)
    result={'passed':True,'component_tests':tests.testsRun}
    if args.replay:
        rows=[json.loads(l) for l in args.replay.read_text(encoding='utf-8').splitlines() if l.strip()]
        verified=evaluate(rows)
        if not verified['passed']: raise SystemExit('Native audit failed: '+json.dumps(verified['errors']))
        reference=json.loads(Path(__file__).with_name('long_native_labels.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            dataset=args.archive
            with zipfile.ZipFile(dataset) as z:
                nested=[n for n in z.namelist() if n.startswith('ocr_dataset_') and n.endswith('.zip')]
                if nested:
                    dataset=Path(tmp)/'dataset.zip'
                    import shutil
                    with z.open(nested[0]) as src,dataset.open('wb') as dst: shutil.copyfileobj(src,dst)
            digest=hashlib.sha256()
            with dataset.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024),b''): digest.update(chunk)
            if digest.hexdigest()!=reference['dataset_sha256']: raise SystemExit('Wrong dataset for independent labels')
            print('Symulacja cooldown offline: 5281 klatek, bez OCR, gry i OBS.',flush=True)
            result.update(native_replay(rows,reference,dataset))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));print('Wynik: '+str(args.output.resolve()))
    if not result['passed']: raise SystemExit(1)

if __name__=='__main__': main()
