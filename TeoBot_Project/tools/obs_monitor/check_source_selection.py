import unittest
from source_selection import select_source
from dual_source import ConfirmationGate


def top(current, maximum=195):
    return {'raw':[f'{current}/{maximum}'],'value':{'current':current,'maximum':maximum,'percent':100*current/maximum}}


def evidence(lo=55,hi=59):
    return {'top':{'available':True,'lower_percent':lo,'upper_percent':hi},
            'sidebar':{'available':False,'reason':'noncontiguous_or_occluded'}}


class Tests(unittest.TestCase):
    def test_missing_top_uses_current_only_not_invented_maximum(self):
        r=select_source({'raw':[''],'value':None},{'current':111},evidence(),195)
        self.assertEqual(r['value']['current'],111)
        self.assertIsNone(r['value']['maximum'])
        self.assertIsNone(r['value']['percent'])

    def test_shortened_side_does_not_veto_supported_top(self):
        r=select_source(top(111),{'current':1},evidence(),195)
        self.assertEqual(r['verification'],'top_color_supported')
        self.assertEqual(r['value']['current'],111)

    def test_bad_top_maximum_selects_side(self):
        r=select_source(top(111,1634),{'current':111},evidence(),195)
        self.assertEqual(r['quality'],'current_only')
        self.assertIsNone(r['value']['maximum'])

    def test_color_cannot_resolve_close_disagreement(self):
        r=select_source(top(111),{'current':112},evidence(),195)
        self.assertIsNone(r['value'])
        self.assertEqual(r['verification'],'conflict')

    def test_conflicting_visible_bars_and_unknown_color_block(self):
        e=evidence();e['sidebar']={'available':True,'lower_percent':0,'upper_percent':2}
        self.assertIsNone(select_source(top(111),{'current':111},e,195)['value'])
        self.assertIsNone(select_source(top(111),{'current':111},{'top':{'available':False}},195)['value'])

    def test_two_clean_counters_with_explicit_bar_occlusion_need_temporal_confirmation(self):
        e={'top':{'available':False,'reason':'noncontiguous_or_occluded'},
           'sidebar':{'available':False,'reason':'foreign_color_overlay'}}
        r=select_source(top(35,150),{'current':35},e,150)
        self.assertEqual(r['verification'],'current_agrees_without_color')
        gate=ConfirmationGate(allow_color_supported=True)
        self.assertIsNone(gate.apply(r,1.)['value'])
        self.assertEqual(gate.apply(r,1.1)['value']['current'],35)
        strict=ConfirmationGate()
        self.assertIsNone(strict.apply(r,1.2)['value'])
        self.assertIsNone(select_source(top(35,150),{'current':34},e,150)['value'])
        self.assertIsNone(select_source(top(35,151),{'current':35},e,150)['value'])
        self.assertIsNone(select_source(top(35,150),{'current':35,'reason':'foreign_color_overlay'},e,150)['value'])
        e['top']={'available':True,'lower_percent':0,'upper_percent':2}
        self.assertIsNone(select_source(top(35,150),{'current':35},e,150)['value'])

    def test_glyph_corroborated_top_without_bar_requires_known_maximum_and_stability(self):
        ev={'top':{'available':False,'reason':'noncontiguous_or_occluded'},
            'sidebar':{'available':False,'reason':'foreign_color_overlay'}}
        t=top(9,150);side={'current':None,'reason':'foreign_color_overlay'}
        self.assertIsNone(select_source(t,side,ev,150)['value'])
        t['glyph_corroborated']=True
        result=select_source(t,side,ev,150)
        self.assertEqual(result['value']['current'],9)
        gate=ConfirmationGate(allow_color_supported=True)
        self.assertIsNone(gate.apply(result,1.)['value'])
        self.assertEqual(gate.apply(result,1.1)['value']['current'],9)
        self.assertIsNone(select_source(t,side,ev,151)['value'])
        ev['top']={'available':True,'lower_percent':70,'upper_percent':80}
        self.assertIsNone(select_source(t,side,ev,150)['value'])

    def test_changing_current_requires_two_full_color_supported_pairs(self):
        gate=ConfirmationGate(allow_color_supported=True)
        r=select_source(top(111),{'current':111},evidence(),195)
        self.assertIsNone(gate.apply(r,1.)['value'])
        r2=select_source(top(110),{'current':110},evidence(),195)
        confirmed=gate.apply(r2,1.1)
        self.assertEqual(confirmed['value']['current'],110)
        self.assertEqual(confirmed['confirmation'],'two_frames_consistent_change')
        # Single-source changes still wait. No extension of freshness window.
        side=select_source({'value':None},{'current':109},evidence(),195)
        self.assertIsNone(gate.apply(side,1.2)['value'])
        self.assertIsNone(gate.apply(select_source({'value':None},{'current':110},evidence(),195),1.3)['value'])
        self.assertIsNone(gate.apply(r,2.)['value'])
        strict=ConfirmationGate()
        self.assertIsNone(strict.apply(r,1.)['value'])
        self.assertIsNone(strict.apply(r2,1.1)['value'])

    def test_slow_confirmation_accepts_gap_and_long_interruption_resets(self):
        gate=ConfirmationGate(max_gap=5.,allow_color_supported=True)
        r=select_source(top(111),{'current':111},evidence(),195)
        self.assertIsNone(gate.apply(r,1.)['value'])
        self.assertEqual(gate.apply(r,1.5)['value']['current'],111)
        self.assertEqual(gate.apply(r,4.)['value']['current'],111)
        self.assertIsNone(gate.apply(r,9.1)['value'])
        self.assertEqual(gate.apply(r,9.3)['value']['current'],111)

    def test_temporal_confirmation_preserves_same_current_across_source_change(self):
        gate=ConfirmationGate(allow_color_supported=True)
        r=select_source({'value':None},{'current':111},evidence(),195)
        self.assertIsNone(gate.apply(r,1.)['value'])
        self.assertEqual(gate.apply(r,1.1)['value']['current'],111)
        switched=select_source(top(111),{'current':None},evidence(),195)
        self.assertEqual(gate.apply(switched,1.2)['value']['current'],111)
        self.assertEqual(gate.apply(switched,1.3)['value']['current'],111)
        self.assertIsNone(gate.apply(dict(switched,value=None),1.4)['value'])
        self.assertIsNone(gate.apply(switched,1.5)['value'])


if __name__=='__main__':unittest.main()

class TransitionTests(unittest.TestCase):
    def test_pair_confirms_change_after_single_source(self):
        gate=ConfirmationGate(max_gap=5.,allow_color_supported=True)
        side=select_source({'value':None},{'current':111},evidence(),195)
        self.assertIsNone(gate.apply(side,1.)['value'])
        pair=select_source(top(110),{'current':110},evidence(),195)
        self.assertEqual(gate.apply(pair,1.1)['value']['current'],110)

    def test_changed_maximum_still_waits(self):
        gate=ConfirmationGate(max_gap=5.,allow_color_supported=True)
        r=select_source(top(111),{'current':111},evidence(),195)
        gate.apply(r,1.)
        changed=dict(r,value=dict(r['value'],maximum=196))
        self.assertIsNone(gate.apply(changed,1.1)['value'])

class CoveredMaximumTests(unittest.TestCase):
    def test_changed_maximum_with_covered_top_uses_cached_side(self):
        r=select_source({'value':{'current':210,'maximum':218}}, {'current':210},
            {'top':{'available':False,'reason':'neutral_overlay'},
             'sidebar':{'available':True,'lower_percent':96.27,'upper_percent':100}},210)
        self.assertEqual(r['value']['current'],210)
        self.assertIsNone(r['value']['maximum'])
        self.assertEqual(r['value']['last_confirmed_maximum'],210)

class MaximumChangeFullResourceTests(unittest.TestCase):
    def test_small_maximum_misread_at_low_hp_never_updates_cache(self):
        r=select_source({'value':{'current':57,'maximum':193}}, {'current':57},
            {'top':{'available':True,'lower_percent':28.8,'upper_percent':30.1},
             'sidebar':{'available':True,'lower_percent':26,'upper_percent':34}},195)
        self.assertIsNone(r['value']['maximum'])
        self.assertEqual(r['value']['last_confirmed_maximum'],195)
    def test_genuine_full_resource_change_is_allowed(self):
        r=select_source({'value':{'current':200,'maximum':200}}, {'current':200},
            {'top':{'available':True,'lower_percent':99,'upper_percent':100},
             'sidebar':{'available':True,'lower_percent':96,'upper_percent':100}},195)
        self.assertEqual(r['value']['maximum'],200)
