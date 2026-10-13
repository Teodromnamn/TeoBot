import unittest
from check_native_response_time import analyze

class Tests(unittest.TestCase):
    def run_case(self,values,confirmed,times):
        n=len(values);ref={'frames':n,'hp':[[i,i,x,100] for i,x in enumerate(values)],'mp':[[0,n-1,50,100]]}
        rows=[]
        for i,x in enumerate(values):
            for r,v in [('hp',x),('mp',50)]:
                rows.append({'case':f'case_{i:05d}','resource':r,'selected':{'value':{'current':v}},
                             'confirmed':{'value':{'current':v} if r=='mp' or confirmed[i] else None},'ms':3})
        return analyze(rows,ref,times)
    def test_actual_recorded_spacing_and_recovery(self):
        a=self.run_case([90,10,10],[True,False,True],[0,.1,.37])
        self.assertEqual(a['resources']['hp']['confirmation_delay']['max_ms'],270)
        self.assertEqual(a['resources']['hp']['closed_gap_duration']['max_ms'],270)
    def test_short_value_is_not_matched_to_later_same_value(self):
        a=self.run_case([90,10,20,10],[True,False,True,True],[0,.1,.2,.3])
        self.assertEqual(len(a['resources']['hp']['never_confirmed_before_next_change']),1)
    def test_trailing_gap_is_unknown(self):
        a=self.run_case([90,10],[True,False],[0,.1]);g=a['resources']['hp']['availability_gaps'][0]
        self.assertTrue(g['open_at_end']);self.assertIsNone(g['duration_recorded_ms'])
    def test_nonmonotonic_clock_rejected(self):
        with self.assertRaises(ValueError):self.run_case([90,10],[True,True],[1,0])
    def test_ambiguous_selected_is_not_ground_truth_but_cannot_be_confirmed(self):
        ref={'frames':1,'hp':[[0,0,None,100]],'mp':[[0,0,50,100]]}
        rows=[{'case':'case_00000','resource':'hp','selected':{'value':{'current':90}},'confirmed':{'value':None}},
              {'case':'case_00000','resource':'mp','selected':{'value':{'current':50}},'confirmed':{'value':{'current':50}}}]
        self.assertTrue(analyze(rows,ref,[0])['passed'])
        rows[0]['confirmed']['value']={'current':90}
        self.assertFalse(analyze(rows,ref,[0])['passed'])

    def test_wrong_confirmed_value_fails(self):
        ref={'frames':1,'hp':[[0,0,10,100]],'mp':[[0,0,50,100]]}
        rows=[{'case':'case_00000','resource':r,'selected':{'value':{'current':v}},'confirmed':{'value':{'current':v}}} for r,v in [('hp',90),('mp',50)]]
        self.assertFalse(analyze(rows,ref,[0])['passed'])

if __name__=='__main__':unittest.main()
