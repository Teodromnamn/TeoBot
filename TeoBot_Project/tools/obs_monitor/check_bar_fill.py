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

    def test_sidebar_magenta_icon_above_body_invalidates_fill(self):
        for resource,color in [('hp',(0,0,180)),('mp',(180,60,0))]:
            full=np.full((10,100,3),color,dtype=np.uint8)
            image=full.copy();image[:,65:]=30
            image[:4,35:47]=(180,0,180)
            image[4:8,35:47]=70
            result=FillEvidence(full,resource,sidebar=True).measure(image)
            self.assertFalse(result['available'])
            self.assertEqual(result['reason'],'foreign_color_overlay')

    def test_hp_blue_empty_background_is_not_an_icon(self):
        full=np.full((10,100,3),(0,0,180),dtype=np.uint8)
        partial=full.copy();partial[:,30:]=(130,80,40)
        result=FillEvidence(full,'hp',sidebar=True).measure(partial)
        self.assertTrue(result['available'])
        self.assertLess(result['upper_percent'],40)

    def test_sidebar_clean_partial_remains_available(self):
        for resource,color in [('hp',(0,0,180)),('mp',(180,60,0))]:
            full=np.full((10,100,3),color,dtype=np.uint8)
            image=full.copy();image[:,65:]=30
            self.assertTrue(FillEvidence(full,resource,sidebar=True).measure(image)['available'])

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




class NativeSidebarContourTests(unittest.TestCase):
    """Real bar pixels: occlusion must not veto a readable top source."""
    @classmethod
    def setUpClass(cls):
        import json, base64, cv2
        from pathlib import Path
        cls.fixture = json.loads(Path(__file__).with_name('sidebar_contour_cases.json').read_text())
        cls.decode = staticmethod(lambda text: cv2.imdecode(np.frombuffer(base64.b64decode(text),np.uint8),1))
        cls.models = {r:FillEvidence(cls.decode(im),r,True) for r,im in cls.fixture['calibration'].items()}

    def test_real_item_borders_and_gray_popups_do_not_veto_top(self):
        from source_selection import select_source
        for case in self.fixture['covered']:
            with self.subTest(case=case['case'],resource=case['resource']):
                measured = self.models[case['resource']].measure(self.decode(case['image']))
                self.assertFalse(measured['available'])
                top = {'value':{'current':case['current'],'maximum':case['maximum']}}
                result = select_source(top,case['side'],{'top':case['top_fill'],'sidebar':measured},case['maximum'])
                self.assertEqual(result['value']['current'],case['current'])
                self.assertTrue(result['source_checks']['top_color_consistent'])

    def test_wrong_top_number_is_rejected_even_if_sidebar_is_unavailable(self):
        from source_selection import select_source
        result = select_source({'value':{'current':108,'maximum':215}},
            {'current':None}, {'top':{'available':True,'lower_percent':46.84,'upper_percent':49.34},
            'sidebar':{'available':False,'reason':'sidebar_contour_occluded'}},215)
        self.assertIsNone(result['value'])

    def test_native_full_and_empty_tail_preserve_contour(self):
        for case in self.fixture['clean']:
            with self.subTest(resource=case['resource']):
                self.assertTrue(self.models[case['resource']].measure(self.decode(case['image']))['available'])

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

class TopForeignOverlayTests(unittest.TestCase):
    def test_mana_item_at_edge_is_unavailable(self):
        full=np.full((14,770,3),(180,60,0),np.uint8)
        image=np.full_like(full,30);image[:,337:]=full[:,337:]
        image[:,334:350]=(0,180,180)
        evidence=FillEvidence(full,'mp').measure(image)
        self.assertFalse(evidence['available'])
        self.assertEqual(evidence['reason'],'foreign_color_overlay')
    def test_gold_suffix_does_not_hide_clean_mana_evidence(self):
        full=np.full((14,770,3),(180,60,0),np.uint8)
        image=np.full_like(full,30);image[:,337:]=full[:,337:]
        image[4:10,424:428]=(0,180,180)
        self.assertTrue(FillEvidence(full,'mp').measure(image)['available'])
    def test_hp_color_changes_remain_valid_but_blue_item_is_unknown(self):
        full=np.full((14,770,3),(0,180,0),np.uint8)
        model=FillEvidence(full,'hp')
        for color in [(0,0,180),(0,180,180)]:
            image=np.full_like(full,30);image[:,:337]=color
            self.assertTrue(model.measure(image)['available'])
        image[:,330:345]=(180,60,0)
        self.assertFalse(model.measure(image)['available'])

if __name__ == '__main__':
    unittest.main()
