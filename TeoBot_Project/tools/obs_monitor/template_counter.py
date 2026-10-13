"""Experimental fixed-font current counters; no Tesseract or live actions."""
import hashlib
from collections import Counter,defaultdict
import cv2
import numpy as np
from benchmark_hp_mp import prepare
from glyph_ocr import groups,is_slash

def parts(crop,source):
    image=np.where(crop.min(axis=2)>140,0,255).astype('uint8')
    rows=np.flatnonzero(np.any(image<128,axis=1))
    if len(rows) and np.count_nonzero(image[rows[-1]]<128)>image.shape[1]*.65:image[max(0,rows[-1]-1):rows[-1]+1]=255
    glyphs=[p for p in groups(image) if p.shape[0]>=6]
    if source=='top':
        slash=next((i for i,p in enumerate(glyphs) if is_slash(p)),None)
        if slash is None:return []
        glyphs=glyphs[:slash]
    return glyphs

def normalize(glyph):
    return (cv2.resize((glyph<128).astype('uint8'),(20,32),interpolation=cv2.INTER_NEAREST)>0).astype('uint8')

class TemplateCounter:
    def __init__(self,model,max_error=.16,min_margin=.06):
        self.max_error=max_error;self.min_margin=min_margin
        self.templates={s:{d:[(np.array([[int(c) for c in row] for row in v['mask']],np.uint8),v['aspect']) for v in vs] for d,vs in digits.items()} for s,digits in model['templates'].items()}
    def read(self,crop,source):
        glyphs=parts(crop,source)
        if not glyphs or len(glyphs)>8:return {'current':None,'reason':'invalid_glyph_count'}
        digits=[];details=[]
        for glyph in glyphs:
            mask=normalize(glyph);aspect=glyph.shape[1]/glyph.shape[0];scores=[]
            for digit,variants in self.templates[source].items():
                best=1.
                for reference,ratio in variants:
                    if abs(np.log(aspect/ratio))>.3:continue
                    union=np.count_nonzero(mask|reference)
                    distance=1-np.count_nonzero(mask&reference)/max(1,union)+min(.5,abs(np.log(aspect/ratio)))*.25
                    best=min(best,distance)
                scores.append((best,digit))
            scores.sort();first,second=scores[:2];margin=second[0]-first[0]
            details.append({'digit':first[1],'error':round(first[0],5),'margin':round(margin,5)})
            if first[0]>self.max_error or margin<self.min_margin:return {'current':None,'reason':'glyph_not_distinct','glyphs':details}
            digits.append(first[1])
        return {'current':int(''.join(digits)),'reason':None,'glyphs':details}

def build_model(samples):
    counts=defaultdict(Counter);patterns={};seen=0
    for crop,source,label in samples:
        glyphs=parts(crop,source)
        if len(glyphs)!=len(str(label)):continue
        for digit,glyph in zip(str(label),glyphs):
            mask=normalize(glyph);aspect=round(glyph.shape[1]/glyph.shape[0],3)
            key=hashlib.sha256(mask.tobytes()+str(aspect).encode()).hexdigest()
            counts[source,digit][key]+=1;patterns[key]={'mask':[''.join(map(str,row.tolist())) for row in mask],'aspect':aspect}
        seen+=1
    templates={s:{} for s in ('top','side')}
    for (source,digit),counter in counts.items():templates[source][digit]=[dict(patterns[key],training_count=count) for key,count in counter.most_common(1)]
    missing={s:sorted(set('0123456789')-set(templates[s])) for s in templates}
    if any(missing.values()):raise ValueError('Missing training digits: '+str(missing))
    return {'schema':1,'method':'normalized_glyph_iou_with_aspect_and_runner_up_margin','training_samples':seen,'templates':templates}
