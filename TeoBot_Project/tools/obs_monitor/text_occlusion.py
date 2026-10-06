"""Conservative pre-OCR detection of neutral objects crossing top counter text."""
import cv2
import numpy as np


def inspect_top_text(crop):
    if crop.size == 0:
        return {'occluded':True,'reason':'empty_crop'}
    height,width=crop.shape[:2]
    # Counter text is centered in the calibrated top bar. Include maximum and
    # the MP suffix without inspecting unrelated objects near the bar ends.
    half=max(50,height*5)
    left=max(0,width//2-half);right=min(width,width//2+half)
    roi=crop[:,left:right]
    _,sat,val=cv2.split(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV))
    neutral=((sat<80)&(val>100)).astype(np.uint8)
    # The neutral beveled rim can connect otherwise normal glyphs.
    neutral[:2]=0;neutral[-2:]=0
    _,_,stats,_=cv2.connectedComponentsWithStats(neutral,8)
    for x,y,w,h,area in stats[1:]:
        if h>=max(6,height-4) and w>=4 and area>=height*3:
            return {'occluded':True,'reason':'tall_neutral_object','rectangle':[left+int(x),int(y),int(w),int(h)]}
    if np.count_nonzero(((sat<45)&(val>125))[2:-2])>max(1,(height-4))*roi.shape[1]*.25:
        return {'occluded':True,'reason':'bright_neutral_popup'}
    return {'occluded':False,'reason':None}


def unavailable(evidence):
    return {'raw':[],'value':None,'text_occlusion':evidence,'ocr_skipped':True,
            'reason':'top_text_occluded'}
