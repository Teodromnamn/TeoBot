import unittest
from window_state import WindowGuard

class Backend:
    value=('OK',True)
    def state(self):return self.value

class Tests(unittest.TestCase):
    def test_minimize_resume_and_inactive(self):
        b=Backend();now=[1.];g=WindowGuard(backend=b,clock=lambda:now[0])
        self.assertEqual(g.check()['status'],'OK')
        b.value=('OK',False)
        self.assertEqual(g.check()['status'],'OK')
        b.value=('GRA_ZMINIMALIZOWANA',False)
        self.assertEqual(g.check()['status'],'GRA_ZMINIMALIZOWANA')
        b.value=('OK',True)
        self.assertEqual(g.check()['status'],'WZNAWIANIE_OBRAZU')
        now[0]=1.9;self.assertEqual(g.check()['status'],'WZNAWIANIE_OBRAZU')
        now[0]=2.;self.assertEqual(g.check()['status'],'OK')
    def test_missing_hidden_ambiguous_and_api_failure_block(self):
        b=Backend();g=WindowGuard(backend=b)
        for status in ['BRAK_OKNA_GRY','OKNO_GRY_UKRYTE','NIEJEDNOZNACZNE_OKNO_GRY']:
            b.value=(status,None);self.assertEqual(g.check()['status'],status)
        b.state=lambda:1/0
        self.assertEqual(g.check()['status'],'BLAD_STANU_OKNA')
