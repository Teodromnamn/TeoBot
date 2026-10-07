import unittest
import numpy as np
from bar_fill import FillEvidence, validate_fill
from dual_source import ConfirmationGate


class Tests(unittest.TestCase):
    def test_wrong_maximum_cannot_pass_repeated_ocr_agreement(self):
        full = np.full((8,100,3),(0,180,0),dtype=np.uint8)
        partial = full.copy()
        partial[:,53:] = 30
        evidence = {'top':FillEvidence(full,'hp').measure(partial)}
        good = {'value':{'current':103,'maximum':195},'verification':'current_agrees'}
        self.assertEqual(validate_fill(good,evidence)['fill_status'],'consistent')
        bad = dict(good,value={'current':103,'maximum':1634})
        gate = ConfirmationGate()
        for now in (1.,1.1,1.2):
            checked = validate_fill(bad,evidence)
            self.assertEqual(checked['fill_status'],'conflict')
            self.assertIsNone(gate.apply(checked,now)['value'])

    def test_gray_popup_tail_is_unknown_not_shorter_fill(self):
        full=np.full((10,770,3),(0,180,0),dtype=np.uint8)
        covered=full.copy();covered[:,320:750]=190;covered[:,750:]=30
        result=FillEvidence(full,'hp').measure(covered)
        self.assertFalse(result['available'])
        self.assertEqual(result['reason'],'neutral_overlay')
        clean=full.copy();clean[:,600:]=30;clean[2:8,370:374]=255
        self.assertTrue(FillEvidence(full,'hp').measure(clean)['available'])

    def test_neutral_cursor_at_edge_is_unknown(self):
        full=np.full((14,770,3),(0,180,0),dtype=np.uint8)
        covered=full.copy();covered[:,393:]=30;covered[:,369:388]=170
        self.assertEqual(FillEvidence(full,'hp').measure(covered)['reason'],'neutral_overlay')

    def test_internal_occlusion_yields_unknown_instead_of_guess(self):
        full = np.full((8,100,3),(0,180,0),dtype=np.uint8)
        partial = full.copy()
        partial[:,60:] = 30
        partial[:,20:40] = 30
        self.assertFalse(FillEvidence(full,'hp').measure(partial)['available'])

    def test_hp_color_change_and_layout_change(self):
        full = np.full((8,100,3),(0,180,0),dtype=np.uint8)
        low = np.full_like(full,30)
        low[:,:20] = (0,0,180)
        model = FillEvidence(full,'hp')
        result = model.measure(low)
        self.assertTrue(result['lower_percent'] <= 20 <= result['upper_percent'])
        self.assertFalse(model.measure(low[:,:80])['available'])

    def test_sidebar_icon_at_fill_edge_is_not_shorter_fill(self):
        full=np.full((10,100,3),(180,0,0),dtype=np.uint8)
        partial=full.copy();partial[4:6,24:]=30
        partial[:,17:24]=(10,180,220)
        evidence=FillEvidence(full,'mp',sidebar=True).measure(partial)
        self.assertFalse(evidence['available'])
        self.assertEqual(evidence['reason'],'foreign_color_overlay')

    def test_half_pixel_rounding_supports_boundary_without_large_tolerance(self):
        full=np.full((10,858,3),(0,180,0),dtype=np.uint8)
        partial=full.copy();partial[:,451:]=30
        e=FillEvidence(full,'hp').measure(partial)
        self.assertTrue(e['lower_percent'] <= 100*103/195 <= e['upper_percent'])
        self.assertFalse(e['lower_percent'] <= 100*111/195 <= e['upper_percent'])

    def test_sidebar_colored_bevel_is_not_fill(self):
        full = np.full((10,100,3),(180,0,0),dtype=np.uint8)
        partial = full.copy()
        partial[4:6,30:] = 30
        result = FillEvidence(full,'mp',sidebar=True).measure(partial)
        self.assertTrue(result['available'])
        self.assertLess(result['upper_percent'],40)


if __name__ == '__main__':
    unittest.main()

class ManaDirectionTests(unittest.TestCase):
    def test_top_mana_right_fill_and_sidebar_left_fill(self):
        full=np.full((14,100,3),(180,60,0),np.uint8)
        for sidebar in [False,True]:
            image=np.full_like(full,30)
            if sidebar:image[:,:20]=full[:,:20]
            else:image[:,80:]=full[:,80:]
            result=FillEvidence(full,'mp',sidebar=sidebar).measure(image)
            self.assertTrue(result['available'])
            self.assertLessEqual(result['lower_percent'],20)
            self.assertGreaterEqual(result['upper_percent'],20)
            self.assertLess(result['upper_percent'],30)
    def test_bevel_joining_counter_is_not_overlay(self):
        full=np.full((14,100,3),(0,180,0),np.uint8)
        full[:2,:]=150
        image=full.copy();image[:,50:]=30
        image[:2,:]=150
        image[2:11,40:42]=255
        self.assertTrue(FillEvidence(full,'hp').measure(image)['available'])
