"""Regression: clipped 110/110 -> 11/11 must yield readable sidebar 110."""
import json
from pathlib import Path
import unittest
from source_selection import select_source
from dual_source import ConfirmationGate


def fills():
    return {'top':{'available':True,'lower_percent':97.74,'upper_percent':100},
            'sidebar':{'available':True,'lower_percent':96.27,'upper_percent':100}}

class Tests(unittest.TestCase):
    def test_clipped_ratio_does_not_override_full_sidebar(self):
        r=select_source({'raw':['11/11'],'value':{'current':11,'maximum':11}},
                        {'raw':'110','current':110},fills(),110)
        self.assertEqual(r['value']['current'],110)
        self.assertEqual(r['source'],'side_text')
        self.assertIsNone(r['value']['maximum'])
        self.assertEqual(r['value']['last_confirmed_maximum'],110)

    def test_wrong_value_does_not_enter_confirmation(self):
        gate=ConfirmationGate(max_gap=5,allow_color_supported=True)
        prior=select_source({'value':{'current':110,'maximum':110}},
                            {'current':110},fills(),110)
        gate.apply(prior,1.)
        clipped=select_source({'value':{'current':11,'maximum':11}},
                              {'current':110},fills(),110)
        self.assertEqual(gate.apply(clipped,1.1)['value']['current'],110)

    def test_current_only_primary_still_works_when_sidebar_missing(self):
        r=select_source({'value':{'current':110,'maximum':110}},
                        {'current':None,'reason':'foreign_color_overlay'},fills(),105)
        self.assertEqual(r['value']['current'],110)
        self.assertIsNone(r['value']['maximum'])
        self.assertEqual(r['value']['last_confirmed_maximum'],105)

    def test_new_full_maximum_can_still_be_observed(self):
        r=select_source({'value':{'current':110,'maximum':110}},
                        {'current':110},fills(),105)
        self.assertEqual(r['value']['maximum'],110)

    def test_readable_disagreement_is_not_silently_overridden(self):
        r=select_source({'value':{'current':110,'maximum':110}},
                        {'current':11},fills(),105)
        self.assertIsNone(r['value'])



def native_check(archive):
    import zipfile
    import cv2
    import numpy as np
    from test_obs_tesseract import Engine,binary,recognize_top
    from benchmark_hp_mp import prepare
    from dual_source import recognize_side,side_text_left
    from text_occlusion import inspect_top_text
    mp=[110,110,110,110,83,86,89,92,92,95,95,98,98,98]
    errors=[];same_frame=0;selected=0
    engine=Engine(r'C:\Program Files\Tesseract-OCR' if __import__('os').name=='nt' else '/usr/share/tesseract-ocr/5')
    try:
        with zipfile.ZipFile(archive) as z:
            cases=sorted(n.rsplit('/',1)[0] for n in z.namelist() if n.endswith('/reading.json'))
            if len(cases)!=14: raise ValueError('Expected the 14-case 214426 diagnostic archive')
            left={r:side_text_left(cv2.imdecode(np.frombuffer(z.read('case_002/'+r+'_side_original.png'),np.uint8),1)) for r in ('hp','mp')}
            for i,c in enumerate(cases):
                meta=json.loads(z.read(c+'/reading.json'))
                full=cv2.imdecode(np.frombuffer(z.read(c+'/full_frame.png'),np.uint8),1)
                for index,r in enumerate(('hp','mp')):
                    images={}
                    for kind,key in [('top_original','top_rectangles'),('side_original','side_rectangles'),('side_bar','side_bar_rectangles')]:
                        image=cv2.imdecode(np.frombuffer(z.read(c+'/'+r+'_'+kind+'.png'),np.uint8),1)
                        x,y,w,h=meta[key][index]
                        if not np.array_equal(image,full[y:y+h,x:x+w]): errors.append([c,r,kind,'not_same_frame'])
                        same_frame+=1;images[kind]=image
                    top=recognize_top(engine,binary(prepare(images['top_original'],'dynamic')),True,
                                      raw_crop=images['top_original'],resource=r)
                    side=recognize_side(engine,images['side_original'],glyph_retry=True,text_left=left[r])
                    evidence=meta['analysis']['readings'][index]['fill']
                    result=select_source(top,side,evidence,205 if r=='hp' else 110)
                    expected=205 if r=='hp' else mp[i]
                    value=result.get('value')
                    if value is None or value['current']!=expected: errors.append([c,r,'wrong_or_missing_current',value,expected])
                    else:selected+=1
                    if i in (2,3) and r=='mp' and not inspect_top_text(images['top_original'],r)['occluded']:
                        errors.append([c,r,'popup_edge_not_detected'])
    finally:engine.tess.close()
    report={'passed':not errors,'independently_labeled_resources':28,'correct_selected':selected,
            'same_frame_comparisons':same_frame,'errors':errors,
            'note':'Fresh OCR and source selection; visual labels. Saved fill measurements reused; temporal confirmation not replayed.'}
    print(json.dumps(report));return not errors


if __name__=='__main__':
    import sys
    if len(sys.argv)==2: raise SystemExit(0 if native_check(sys.argv[1]) else 1)
    unittest.main()
