import unittest
from run_template_regression import candidate_status,csv_labels,current,bundle_inputs
import tempfile,zipfile
from pathlib import Path

class Tests(unittest.TestCase):
    def out(self,a,b):return {'top':{'current':a},'side':{'current':b}}
    def test_correct_top_available_despite_wrong_side(self):
        self.assertEqual(candidate_status(self.out(14,4),14),('candidate_correct_available',True))
    def test_correct_fallback(self):
        self.assertEqual(candidate_status(self.out(None,111),111),('candidate_correct_available',False))
    def test_all_missing(self):
        self.assertEqual(candidate_status(self.out(None,None),101),('candidate_missing',False))
    def test_only_wrong_source_is_not_success(self):
        self.assertEqual(candidate_status(self.out(None,4),14),('only_wrong_candidates',False))
    def test_no_accuracy_claim_without_label(self):
        self.assertEqual(candidate_status(self.out(144,130),None),('unlabeled',False))
    def test_duplicate_reference_rejected(self):
        with self.assertRaises(ValueError):csv_labels('case,hp_current\na,1\na,2\n')
    def test_bundle_pairs_dataset_and_adjacent_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with zipfile.ZipFile(root/'hp_mp_test.zip','w') as z:
                z.writestr('suite/dataset.zip',b'inner bytes');z.writestr('suite/labels.csv','case,hp_current\na,1\n');z.writestr('other/labels.csv','wrong')
            bundle_inputs(root,root/'out')
            target=root/'out/hp_mp_test/suite'
            self.assertEqual((target/'dataset.zip').read_bytes(),b'inner bytes')
            self.assertEqual((target/'labels.csv').read_text(),'case,hp_current\na,1\n')

    def test_zero_is_a_real_label(self):
        self.assertEqual(current('0'),0);self.assertIsNone(current(''))
if __name__=='__main__':unittest.main()
