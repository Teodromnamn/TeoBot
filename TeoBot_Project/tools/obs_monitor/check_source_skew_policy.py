import itertools,json,subprocess,sys
from pathlib import Path
import argparse
parser=argparse.ArgumentParser();parser.add_argument('suite',type=Path);parser.add_argument('--directory');options=parser.parse_args()
base=options.suite;replay=Path('tools/obs_monitor/replay_hp_mp_dataset.py')
if not replay.is_file():raise SystemExit('Uruchom z TeoBot_Project.')
output=base/'replay_source_skew.jsonl';truth=json.loads((base/'expected.json').read_text());errors=[]
print(f'Test offline rozbieznosci zrodel: {len(truth)} klatek, {2*len(truth)} wartosci...',flush=True)
args=[sys.executable,'-X','utf8',str(replay),str(base/'dataset.zip'),'--resilient-verification','--labels',str(base/'labels.csv')]
if options.directory:args+=['--directory',options.directory]
with output.open('w',encoding='utf-8') as stream:subprocess.run(args,stdout=stream,check=True)
rows=[json.loads(x) for x in output.read_text(encoding='utf-8').splitlines()];ambiguous=resolved=0
for row in rows:
 if 'case'not in row:continue
 known=truth[row['case']][row['resource']]
 expected=known['expected']
 if known['top_digits']==known['side_digits'] and known['top_digits'] in (known['top_fill'],known['side_fill']):
  expected=known['top_digits']
 ambiguous+=expected is None;resolved+=expected is not None
 for kind in ['selected','confirmed']:
  v=row[kind]['value']
  if expected is None:
   if v is not None:errors.append([row['case'],row['resource'],kind,'ambiguous_accepted',v])
  elif v is None:
   if kind=='selected':errors.append([row['case'],row['resource'],kind,'missing'])
  elif v['current']!=expected:errors.append([row['case'],row['resource'],kind,v])
 # Every three-sample consistent block must recover confirmation by its last sample.
 if expected is not None and int(row['case'].split('_')[1])%3==2 and row['confirmed']['value'] is None:errors.append([row['case'],row['resource'],'not_recovered_by_third_frame'])
sys.path.insert(0,str(replay.parent.resolve()))
from source_selection import select_source
component_checks=0
for resource,values,maximum in [('hp',[57,99],195),('mp',[10,80],150)]:
 for reverse in [False,True]:
  values=values[::-1] if reverse else values
  for bits in itertools.product([0,1],repeat=4):
   top,side,top_fill,side_fill=[values[b] for b in bits]
   def evidence(value):
    percent=100*value/maximum
    return {'available':True,'lower_percent':percent-1,'upper_percent':percent+1}
   reading={'raw':[f'{top}/{maximum}'],'value':{'current':top,'maximum':maximum,'percent':100*top/maximum}}
   selected=select_source(reading,{'raw':str(side),'current':side},{'top':evidence(top_fill),'sidebar':evidence(side_fill)},maximum)
   expected=top if top==side and top in (top_fill,side_fill) else (top_fill if top_fill==side_fill and top_fill in (top,side) else None)
   v=selected['value'];component_checks+=1
   if (v is None)!=(expected is None) or (v and v['current']!=expected):errors.append(['component',resource,bits,selected])
report={'errors':len(errors),'examples':errors[:20],'image_samples':resolved+ambiguous,'resolvable_samples':resolved,'expected_ambiguous_rejections':ambiguous,'component_checks':component_checks,'note':'Updated source policy: two matching counters and one supporting fill override the other fill. Different counters retain conservative arbitration. Expected values use independent synthetic construction metadata, not OCR.'}
(base/'source_skew_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(rows[-1],ensure_ascii=False));print(json.dumps(report,ensure_ascii=False));print('Wyslij:',output,base/'source_skew_checks.json')
if errors:raise SystemExit(1)
