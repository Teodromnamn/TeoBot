import unittest
from observation_policy import ObservationPolicy


def payload(current=5,observed=0,valid=True):
    r={'valid':valid,'value':{'current':current} if valid else None,'effective_percent':current,
       'observed_at_unix_ms':observed,'expires_at_unix_ms':observed+5000}
    return {'resources':{'hp':r,'mp':dict(r)}}

class Tests(unittest.TestCase):
    def test_new_frame_after_cooldown_is_needed(self):
        p=ObservationPolicy(10,10,'current',1000)
        self.assertEqual(p.evaluate(payload(),0,0)['hp']['decision'],'would_execute')
        self.assertEqual(p.evaluate(payload(),2000,2000)['hp']['decision'],'repeated_or_old_observation')
        self.assertEqual(p.evaluate(payload(observed=2100),2100,2100)['hp']['decision'],'would_execute')
    def test_loss_does_not_release_cooldown(self):
        p=ObservationPolicy(10,10,'current',1000);p.evaluate(payload(),0,0)
        self.assertEqual(p.evaluate(payload(valid=False),100,100)['hp']['decision'],'unavailable')
        self.assertEqual(p.evaluate(payload(observed=200),200,200)['hp']['decision'],'cooldown')
    def test_expiry_and_slow_frame(self):
        self.assertEqual(ObservationPolicy(10,10).evaluate(payload(),400,400)['hp']['decision'],'would_execute')
        self.assertEqual(ObservationPolicy(10,10).evaluate(payload(),5001,5001)['hp']['decision'],'unavailable')
    def test_range_and_boundary(self):
        p=ObservationPolicy(10,10,'current',0);a=payload(valid=False)
        a['resources']['hp'].update(range_valid=True,value_range={'lower':5,'upper':6})
        self.assertEqual(p.evaluate(a,0,0)['hp']['decision'],'would_execute')
        a['resources']['hp'].update(observed_at_unix_ms=100,value_range={'lower':5,'upper':11})
        self.assertEqual(p.evaluate(a,100,100)['hp']['decision'],'uncertain')
        self.assertEqual(ObservationPolicy(10,10).evaluate(payload(10),0,0)['hp']['decision'],'do_not_execute')
    def test_wall_clock_jump_does_not_release_cooldown(self):
        p=ObservationPolicy(10,10,'current',1000);p.evaluate(payload(),0,0)
        self.assertEqual(p.evaluate(payload(observed=100000),100000,100)['hp']['decision'],'cooldown')
    def test_newer_high_value_prevents_old_low_action(self):
        p=ObservationPolicy(10,10,'current',0);p.evaluate(payload(50,200),200,200)
        self.assertEqual(p.evaluate(payload(5,100),200,201)['hp']['decision'],'repeated_or_old_observation')
    def test_hp_missing_does_not_block_mp(self):
        a=payload();a['resources']['hp']={}
        d=ObservationPolicy(10,10).evaluate(a,0,0)
        self.assertEqual(d['hp']['decision'],'unavailable');self.assertEqual(d['mp']['decision'],'would_execute')
    def test_percentage_uses_accepted_cached_maximum(self):
        a=payload(50);a['resources']['hp'].update(effective_percent=25,maximum_is_cached=True)
        decision=ObservationPolicy(30,10).evaluate(a,0,0)['hp']
        self.assertEqual(decision['decision'],'would_execute')
        self.assertTrue(decision['maximum_is_cached'])

    def test_bad_settings_rejected(self):
        for v in [float('nan'),-1,101]:
            with self.assertRaises(ValueError):ObservationPolicy(v)

if __name__=='__main__':unittest.main()
