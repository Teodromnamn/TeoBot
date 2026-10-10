import unittest
from check_native_threshold_replay import audit


def sample(current=50,maximum=100,confirmed=True):
    value={'current':current,'maximum':maximum}
    return [{'case':'case_00000','resource':r,'confirmed':{'value':value if confirmed else None}}
            for r in ('hp','mp')]

REF={'frames':1,'hp':[[0,0,50,100]],'mp':[[0,0,50,100]]}

class Tests(unittest.TestCase):
    def test_correct_decisions_and_expiry(self):
        result=audit(sample(),REF)
        self.assertTrue(result['passed'])
        self.assertEqual(result['decision_checks'],16)
        self.assertEqual(result['expiry_checks'],16)
        self.assertEqual(result['rules']['hp:current<50']['do_not_execute'],1)

    def test_wrong_current_fails(self):
        result=audit(sample(current=1),REF)
        self.assertFalse(result['passed'])
        self.assertTrue(result['errors'])

    def test_unconfirmed_is_unavailable(self):
        result=audit(sample(confirmed=False),REF)
        self.assertTrue(result['passed'])
        self.assertEqual(result['rules']['hp:current<100']['unavailable'],1)
        self.assertEqual(result['expiry_checks'],0)

    def test_cached_maximum_difference_reported(self):
        rows=sample()
        rows[0]['confirmed']['value']={'current':50,'maximum':None,'last_confirmed_maximum':65}
        result=audit(rows,REF)
        self.assertTrue(result['passed'])
        self.assertEqual(result['rules']['hp:percent<75']['cached_maximum_threshold_difference'],1)

    def test_missing_or_duplicate_rows_rejected(self):
        with self.assertRaises(ValueError): audit(sample()[:1],REF)
        with self.assertRaises(ValueError): audit(sample()+sample(),REF)

if __name__=='__main__': unittest.main()
