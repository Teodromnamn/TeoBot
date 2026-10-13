"""Live OBS diagnostic with read-only decision logging; never sends keys."""
import argparse
import json
from pathlib import Path
import sys
import time
from observation_policy import ObservationPolicy


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hp-threshold',type=float,default=50)
    p.add_argument('--mp-threshold',type=float,default=25)
    p.add_argument('--threshold-unit',choices=['current','percent'],default='percent')
    p.add_argument('--cooldown-ms',type=float,default=1000)
    args,extra=p.parse_known_args()
    try:policy=ObservationPolicy(args.hp_threshold,args.mp_threshold,args.threshold_unit,args.cooldown_ms)
    except ValueError as e:p.error(str(e))
    import test_obs_pipeline as pipeline
    import run_long_diagnostic as run
    original=pipeline.publish;argv=sys.argv;handle=None;output=None;log_error=None

    def observed_publish(*a,**kw):
        nonlocal handle,output,log_error
        original(*a,**kw)
        publisher=pipeline._result_publisher
        if publisher is None:return
        payload=publisher.snapshot()
        decisions=policy.evaluate(payload,time.time_ns()//1000000,time.monotonic_ns()/1000000)
        record={'published_at_unix_ms':payload['published_at_unix_ms'],'status':payload['status'],
                'result_age_ms':payload.get('result_age_ms'),'slow_reading':payload.get('slow_reading'),
                'mode':'observation_only','decisions':decisions}
        # Diagnostic writes never invalidate the OCR result. Recording failure
        # stays explicit in the final summary instead of silently dropping data.
        if log_error is None:
            try:
                if handle is None:
                    output=publisher.path.parent
                    handle=(output/'observation_decisions.jsonl').open('w',encoding='utf-8')
                handle.write(json.dumps(record)+'\n');handle.flush()
            except OSError as e:
                log_error=str(e);print('Blad zapisu obserwacji: '+log_error,flush=True)
        for r,d in decisions.items():
            if d['decision']=='would_execute':
                print(f"OBSERWACJA: {r.upper()} wykonalbym akcje; zakres {d['lower']}–{d['upper']} {policy.unit}, zrodlo {d['source']}. Bez klawiszy.",flush=True)
        if output is not None and payload['status']=='ZATRZYMANY_PROGRAM':
            try:
                report=policy.summary();report['log_error']=log_error
                (output/'observation_summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            except OSError as e:print('Blad podsumowania obserwacji: '+str(e),flush=True)
    try:
        pipeline.publish=observed_publish;sys.argv=['run_long_diagnostic.py',*extra]
        print('TRYB OBSERWACYJNY: brak wysylania klawiszy. Cooldown to zalozenie testowe.',flush=True)
        run.main()
    finally:
        pipeline.publish=original;sys.argv=argv
        if handle is not None:handle.close()


if __name__=='__main__':main()
