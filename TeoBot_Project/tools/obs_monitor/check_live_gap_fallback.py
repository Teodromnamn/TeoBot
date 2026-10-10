import unittest
from source_selection import select_source


def fill(lo,hi):return {'available':True,'lower_percent':lo,'upper_percent':hi}


class Tests(unittest.TestCase):
    def test_layout_failure_does_not_veto_primary(self):
        r=select_source({'value':{'current':143,'maximum':175}},
            {'current':None,'reason':'layout_or_occlusion'},
            {'top':fill(81.23,81.89),'sidebar':fill(0,3.81)},175)
        self.assertEqual(r['value']['current'],143)
        self.assertTrue(r['source_checks']['sidebar_fill_ignored'])

    def test_impossible_secondary_number_does_not_veto_primary(self):
        r=select_source({'value':{'current':65,'maximum':65}},
            {'current':165}, {'top':fill(97.74,100),'sidebar':fill(92.02,99.47)},65)
        self.assertEqual(r['value']['current'],65)

    def test_changed_max_keeps_current_and_old_max(self):
        r=select_source({'value':{'current':70,'maximum':170}},
            {'current':None,'reason':'digit_count_mismatch'},
            {'top':fill(40.84,41.63),'sidebar':{'available':False}},165)
        self.assertEqual(r['value']['current'],70)
        self.assertIsNone(r['value']['maximum'])
        self.assertEqual(r['value']['last_confirmed_maximum'],165)
        self.assertIn('maximum_update_blocked',r)

    def test_readable_disagreement_is_not_ignored(self):
        r=select_source({'value':{'current':143,'maximum':175}},
            {'current':20}, {'top':fill(81.23,81.89),'sidebar':fill(10,15)},175)
        self.assertIsNone(r['value'])

    def test_unverified_top_ratio_does_not_recover(self):
        r=select_source({'value':{'current':70,'maximum':170}},
            {'current':None,'reason':'digit_count_mismatch'},
            {'top':fill(10,11),'sidebar':{'available':False}},165)
        self.assertIsNone(r['value'])



def check_native_cases(archive_path):
    import json,zipfile,io,os
    import cv2,numpy as np
    from bar_fill import FillEvidence
    from benchmark_hp_mp import prepare
    from test_obs_tesseract import Engine,binary,recognize_top
    from dual_source import recognize_side,side_text_left
    # Independently read from original images: these are labels, not saved OCR.
    cases=[(579,'mp',65,65),(2029,'hp',70,165),(2030,'hp',70,165),(2031,'hp',70,165),
           (2040,'hp',54,165),(2065,'hp',51,165),(2066,'hp',51,165)]
    cases += [(i,'hp',47,165) for i in range(2067,2076)]
    cases += [(i,'hp',143,175) for i in range(4098,4104)]
    cases += [(i,'hp',134,175) for i in [4255,4256,4257,4258,4261,4262,4263,4264]]
    cases += [(179,'hp',150,155),(180,'mp',57,60),(200,'mp',54,60),
              (243,'hp',155,155),(543,'mp',65,65),(2624,'mp',15,75),(4069,'mp',14,80)]
    os.environ['OMP_THREAD_LIMIT']='2'
    engine=Engine(r'C:\Program Files\Tesseract-OCR' if os.name=='nt' else '/usr/share/tesseract-ocr/5')
    errors=[]
    try:
        with zipfile.ZipFile(archive_path) as outer:
            nested=[n for n in outer.namelist() if n.startswith('ocr_dataset_') and n.endswith('.zip')]
            data=zipfile.ZipFile(io.BytesIO(outer.read(nested[0]))) if nested else outer
            def image(path):return cv2.imdecode(np.frombuffer(data.read(path),np.uint8),1)
            for i,r,expected,cached in cases:
                prefix=f'case_{i:05d}/{r}_'
                crop=image(prefix+'top_original.png')
                top=recognize_top(engine,binary(prepare(crop,'dynamic')),True,raw_crop=crop,resource=r)
                left=side_text_left(image(f'case_00000/{r}_side_original.png'))
                side=recognize_side(engine,image(prefix+'side_original.png'),True,text_left=left)
                evidence={name:FillEvidence(image(f'calibration/{r}_{kind}.png'),r,sidebar=name=='sidebar').measure(image(prefix+kind+'.png'))
                          for name,kind in [('top','top_original'),('sidebar','side_bar')]}
                if i==579 and (side.get('current')!=65 or not side.get('ignored_neutral_margin_overlay')):
                    errors.append({'case':i,'resource':r,'reason':'native_neutral_rim_not_detected','side':side})
                selected=select_source(top,side,evidence,cached)
                actual=(selected.get('value') or {}).get('current')
                if actual!=expected:errors.append({'case':i,'resource':r,'expected':expected,'actual':actual})
            if data is not outer:data.close()
    finally:engine.tess.close()
    print(json.dumps({'native_samples':len(cases),'errors':errors,'passed':not errors,
        'note':'Fresh OCR against independently read native crops. Current values checked; cached maxima deliberately retained.'}))
    return not errors


if __name__=='__main__':
    import sys
    if len(sys.argv)==2:
        raise SystemExit(0 if check_native_cases(sys.argv[1]) else 1)
    unittest.main()
