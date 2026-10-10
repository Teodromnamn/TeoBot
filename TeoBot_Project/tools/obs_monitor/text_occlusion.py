"""Conservative pre-OCR detection of foreign objects crossing top counter text."""
import cv2
import numpy as np


def inspect_top_text(crop, resource=None):
    if crop.size == 0:
        return {'occluded':True,'status':'ZASLONIETY','reason':'empty_crop'}
    height,width=crop.shape[:2]
    if resource is None:
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        blue=(hsv[:,:,0]>=95)&(hsv[:,:,0]<=135)&(hsv[:,:,1]>90)
        resource='mp' if np.count_nonzero(blue)>width else 'hp'
    # Counter text is centered in the calibrated top bar. Include maximum and
    # only the main ratio: the colored MP suffix is irrelevant.
    half=max(50,height*5)
    left=max(0,width//2-half);right=min(width,width//2+int(height*(1.7 if resource=='mp' else 2.5)))
    roi=crop[:,left:right]
    _,sat,val=cv2.split(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV))
    # Compare each row with the bar immediately beside the counter. Accept
    # both fill/empty backgrounds and their anti-aliased blends with white text.
    pixels=roi.astype(np.float32)
    distance=np.full(roi.shape[:2],255.,np.float32)
    for lo,hi in [(max(0,left-24),left),(right,min(width,right+24))]:
        if hi<=lo:continue
        background=np.median(crop[:,lo:hi].astype(np.float32),axis=1)[:,None,:]
        direction=255.-background
        alpha=np.clip(np.sum((pixels-background)*direction,axis=2)/
                      np.maximum(1.,np.sum(direction*direction,axis=2)),0.,1.)
        fitted=background+alpha[:,:,None]*direction
        distance=np.minimum(distance,np.max(np.abs(pixels-fitted),axis=2))
    foreign=((sat>70)&(val>70)&(distance>40)).astype(np.uint8)
    # Ignore the bevel, but retain small objects clipping the text from an edge.
    foreign[:2]=0;foreign[-2:]=0
    _,_,objects,_=cv2.connectedComponentsWithStats(foreign,8)
    for x,y,w,h,area in objects[1:]:
        if area>=20 and w>=4 and h>=4:
            return {'occluded':True,'status':'ZASLONIETY','reason':'foreign_colored_object',
                    'rectangle':[left+int(x),int(y),int(w),int(h)],'foreign_pixels':int(area)}
    # Flat gray rectangles are foreign UI fragments, unlike curved glyph ink.
    # Exclude white cores and dark background; inspect connected pixels only.
    gray=((sat<5)&(val>=100)&(val<240)).astype(np.uint8)
    gray[:2]=0;gray[-2:]=0
    _,_,flat,_=cv2.connectedComponentsWithStats(gray,8)
    for x,y,w,h,area in flat[1:]:
        if w>=3 and h>=6 and area>=w*h*.95:
            return {'occluded':True,'status':'ZASLONIETY','reason':'flat_gray_text_overlay',
                    'rectangle':[left+int(x),int(y),int(w),int(h)]}
    neutral=((sat<80)&(val>100)).astype(np.uint8)
    # The neutral beveled rim can connect otherwise normal glyphs.
    neutral[:2]=0;neutral[-2:]=0
    _,_,stats,_=cv2.connectedComponentsWithStats(neutral,8)
    for x,y,w,h,area in stats[1:]:
        if h>=max(6,height-4) and w>=4 and area>=height*3:
            return {'occluded':True,'status':'ZASLONIETY','reason':'tall_neutral_object','rectangle':[left+int(x),int(y),int(w),int(h)]}
    if np.count_nonzero(((sat<45)&(val>125))[2:-2])>max(1,(height-4))*roi.shape[1]*.40:
        return {'occluded':True,'status':'ZASLONIETY','reason':'bright_neutral_popup'}
    return {'occluded':False,'status':'BRAK_OZNAK_ZASLONIECIA','reason':None}


def unavailable(evidence):
    return {'raw':[],'value':None,'text_occlusion':evidence,'ocr_skipped':True,
            'reason':'top_text_occluded'}
