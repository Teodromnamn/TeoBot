import unittest
from source_selection import select_source
from dual_source import ConfirmationGate
from threshold_decision import below_threshold


def reading(a,b,maximum):
    def fill(n):
        p=100*n/maximum
        return {'available':True,'lower_percent':max(0,p-2),'upper_percent':min(100,p+2)}
    return select_source({'value':{'current':a,'maximum':maximum}}, {'current':b},
        {'top':fill(a),'sidebar':fill(b)},maximum)


def resource(interval,confirmed=True):
    return {'valid':False,'range_valid':confirmed,'value_range':interval,'expires_at_unix_ms':2000}


class Tests(unittest.TestCase):
    def confirmed(self,a,b,m):
        gate=ConfirmationGate(max_gap=5,allow_color_supported=True)
        r=reading(a,b,m)
        self.assertIsNone(gate.apply(r,1.)['confirmed_range'])
        result=gate.apply(r,1.1)
        self.assertIsNone(result['value'])
        return result['confirmed_range']

    def test_5_or_6_below_10_percent(self):
        r=resource(self.confirmed(5,6,100))
        self.assertEqual(below_threshold(r,10,'percent',1000)['decision'],'execute')

    def test_11_or_17_below_100_hp(self):
        r=resource(self.confirmed(11,17,1000))
        self.assertEqual(below_threshold(r,100,now_ms=1000)['decision'],'execute')

    def test_straddling_threshold_is_uncertain(self):
        r=resource(self.confirmed(95,105,1000))
        self.assertEqual(below_threshold(r,100,now_ms=1000)['decision'],'uncertain')

    def test_equality_is_not_below(self):
        r=resource(self.confirmed(100,105,1000))
        self.assertEqual(below_threshold(r,100,now_ms=1000)['decision'],'do_not_execute')

    def test_unconfirmed_and_expired_do_not_trigger(self):
        bounds=self.confirmed(5,6,100)
        self.assertEqual(below_threshold(resource(bounds,False),10,now_ms=1000)['decision'],'unavailable')
        self.assertEqual(below_threshold(resource(bounds),10,now_ms=2000)['decision'],'unavailable')

    def test_truncated_1_never_enters_interval(self):
        e={'top':{'available':True,'lower_percent':55,'upper_percent':59},
           'sidebar':{'available':True,'lower_percent':55,'upper_percent':59}}
        r=select_source({'value':{'current':111,'maximum':195}},
            {'current':None,'raw':'1','reason':'digit_count_mismatch'},e,195)
        self.assertNotIn('candidate_range',r)
        self.assertEqual(r['value']['current'],111)

    def test_precise_top_fill_discriminates_wrong_side_number(self):
        r=select_source({'value':{'current':111,'maximum':195}}, {'current':108},
            {'top':{'available':True,'lower_percent':56.8,'upper_percent':57.1},
             'sidebar':{'available':True,'lower_percent':52,'upper_percent':60}},195)
        self.assertNotIn('candidate_range',r)
        self.assertEqual(r['value']['current'],111)

    def test_changing_ranges_preserve_both_frames(self):
        gate=ConfirmationGate(max_gap=5,allow_color_supported=True)
        gate.apply(reading(11,17,1000),1.)
        r=gate.apply(reading(5,6,1000),1.1)['confirmed_range']
        self.assertEqual((r['lower'],r['upper']),(5,17))

    def test_gap_and_loss_reset_confirmation(self):
        gate=ConfirmationGate(max_gap=5,allow_color_supported=True)
        gate.apply(reading(5,6,100),1.)
        self.assertIsNone(gate.apply(reading(5,6,100),6.1)['confirmed_range'])
        gate.apply({'value':None},6.2)
        self.assertIsNone(gate.apply(reading(5,6,100),6.3)['confirmed_range'])

    def test_publication_and_invalidation(self):
        import tempfile,json
        from pathlib import Path
        from test_obs_pipeline import publish
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'latest.json'
            bounds=self.confirmed(5,6,100)
            r={'value':None,'confirmed_range':bounds,'verification':'bounded_conflict','quality':'bounded_conflict'}
            publish(p,'BRAK_ODCZYTU',[r,{}],100,5000,['bounded_conflict','unreadable'])
            data=json.loads(p.read_text())
            hp=data['resources']['hp']
            self.assertTrue(hp['range_valid']);self.assertFalse(hp['valid'])
            self.assertIsNone(data['hp'])
            self.assertEqual(below_threshold(hp,10,'percent',hp['observed_at_unix_ms']+100)['decision'],'execute')
            publish(p,'GRA_ZMINIMALIZOWANA',[r,{}],100,5000,['bounded_conflict','unreadable'])
            hp=json.loads(p.read_text())['resources']['hp']
            self.assertFalse(hp['range_valid'])

if __name__=='__main__':unittest.main()
