"""Read-only threshold/cooldown observer. Contains no input dispatch API."""
from collections import Counter
import math
from threshold_decision import below_threshold


class ObservationPolicy:
    def __init__(self,hp_threshold=50,mp_threshold=25,unit='percent',cooldown_ms=1000):
        if unit not in ('current','percent'):raise ValueError('Invalid threshold unit')
        if any(not math.isfinite(x) or x<0 for x in (hp_threshold,mp_threshold,cooldown_ms)):
            raise ValueError('Thresholds/cooldown must be finite and nonnegative')
        if unit=='percent' and max(hp_threshold,mp_threshold)>100:raise ValueError('Percent threshold exceeds 100')
        self.thresholds={'hp':hp_threshold,'mp':mp_threshold};self.unit=unit;self.cooldown_ms=cooldown_ms
        self.last_action={};self.newest={};self.counts={r:Counter() for r in ('hp','mp')}

    def evaluate(self,payload,wall_ms,monotonic_ms):
        result={}
        for r,threshold in self.thresholds.items():
            resource=payload.get('resources',{}).get(r,{})
            decision=below_threshold(resource,threshold,self.unit,wall_ms)
            status=decision['decision'];observed=resource.get('observed_at_unix_ms')
            old=self.newest.get(r)
            if status in ('execute','do_not_execute','uncertain'):
                if observed is None or not math.isfinite(observed):status='unavailable'
                elif old is not None and observed<=old:status='repeated_or_old_observation'
                else:self.newest[r]=observed
            remaining=max(0,self.cooldown_ms-(monotonic_ms-self.last_action[r])) if r in self.last_action else 0
            if status=='execute':
                if remaining:status='cooldown'
                else:
                    status='would_execute';self.last_action[r]=monotonic_ms
            self.counts[r][status]+=1
            result[r]={**decision,'threshold_decision':decision['decision'],'decision':status,'resource':r,'source':resource.get('source'),
                       'quality':resource.get('quality'),'confirmation':resource.get('confirmation'),
                       'verification':resource.get('verification'),'reading_reason':resource.get('reason'),
                       'text_occlusion':resource.get('text_occlusion'),
                       'value':resource.get('value'),'value_range':resource.get('value_range'),
                       'observed_at_unix_ms':observed,'cooldown_remaining_ms':remaining,
                       'maximum_is_cached':resource.get('maximum_is_cached',False)}
        return result

    def summary(self):
        return {'mode':'observation_only','rules':{'unit':self.unit,'thresholds':self.thresholds,
            'cooldown_ms':self.cooldown_ms,'cooldown_groups':'independent_hp_mp'},
            'decisions':{r:dict(v) for r,v in self.counts.items()},
            'note':'Would-execute starts a simulated cooldown only. No keys, game effect or measured game cooldown.'}
