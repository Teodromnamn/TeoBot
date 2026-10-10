"""Offline native 105 screenshot: real OCR and source selection, no OBS/game."""
import argparse
import base64
import json
from pathlib import Path
import cv2
import numpy as np
from dual_source import recognize_side
from source_selection import select_source
from test_obs_tesseract import Engine

parser=argparse.ArgumentParser()
parser.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
args=parser.parse_args()
fixture=json.loads(Path(__file__).with_name('sidebar_contour_cases.json').read_text())['readable_side_margin']
crop=cv2.imdecode(np.frombuffer(base64.b64decode(fixture['image']),np.uint8),1)
engine=Engine(args.directory)
try:
    side=recognize_side(engine,crop,True,text_left=fixture['text_left'])
    assert side['current']==105,side
    selected=select_source({'value':{'current':108,'maximum':215}},side,
        {'top':{'available':True,'lower_percent':46.84,'upper_percent':49.34},
         'sidebar':{'available':True,'lower_percent':44.02,'upper_percent':51.63}},215)
    assert selected['value']['current']==105 and selected['source']=='side_text',selected
    crop[:,8:11]=(180,0,180)
    covered=recognize_side(engine,crop,True,text_left=8)
    assert covered['current'] is None,covered
    print(json.dumps({'passed':True,'side_raw':side['raw'],'selected_current':105,
        'source':selected['source'],'digit_overlap_rejected':True,
        'note':'Real OCR of one labeled native crop; overlap uses synthetic occlusion.'}))
finally:
    engine.tess.close()
