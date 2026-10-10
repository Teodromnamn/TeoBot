import unittest
from copy import deepcopy
from check_long_native_audit import evaluate


class Tests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'case':'case_01340','resource':'hp','confirmed':{'value':None}},
            {'summary':{'resource_samples':10562,'manually_labeled':10561,
                        'labeled_selected':10561,'labeled_confirmed':10510,
                        'wrong_labeled_selected_current':0,'wrong_labeled_confirmed_current':0,
                        'wrong_labeled_confirmed_maximum':0}}]
    def test_success(self):self.assertTrue(evaluate(self.rows)['passed'])
    def test_wrong_confirmed_current(self):
        self.rows[-1]['summary']['wrong_labeled_confirmed_current']=1
        self.assertFalse(evaluate(self.rows)['passed'])
    def test_ambiguous_cannot_be_confirmed(self):
        self.rows[0]['confirmed']['value']={'current':130}
        self.assertFalse(evaluate(self.rows)['passed'])
    def test_missing_sample_is_failure(self):
        self.rows[-1]['summary']['labeled_selected']=10560
        self.assertFalse(evaluate(self.rows)['passed'])

if __name__=='__main__':unittest.main()
