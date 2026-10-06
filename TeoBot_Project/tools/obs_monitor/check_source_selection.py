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

    def test_temporal_confirmation_resets_on_source_or_cached_maximum_change(self):
        gate=ConfirmationGate(allow_color_supported=True)
        r=select_source({'value':None},{'current':111},evidence(),195)
        self.assertIsNone(gate.apply(r,1.)['value'])
        self.assertEqual(gate.apply(r,1.1)['value']['current'],111)
        switched=select_source(top(111),{'current':None},evidence(),195)
        self.assertIsNone(gate.apply(switched,1.2)['value'])
        self.assertEqual(gate.apply(switched,1.3)['value']['current'],111)
        self.assertIsNone(gate.apply(dict(switched,value=None),1.4)['value'])
        self.assertIsNone(gate.apply(switched,1.5)['value'])


if __name__=='__main__':unittest.main()
