"""Vectorized equivalent of TemplateCounter; thresholds and outputs unchanged."""
import numpy as np
from template_counter import TemplateCounter,parts,normalize

class VectorizedTemplateCounter(TemplateCounter):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.packed={}
        for source,ds in self.templates.items():
            digits=sorted(ds);masks=[];aspects=[];ids=[]
            for i,d in enumerate(digits):
                for mask,aspect in ds[d]:masks.append(mask);aspects.append(aspect);ids.append(i)
            masks=np.stack(masks)
            self.packed[source]=(digits,masks,np.asarray(aspects),np.asarray(ids),np.count_nonzero(masks,axis=(1,2)))

    def read(self,crop,source):
        glyphs=parts(crop,source)
        if not glyphs or len(glyphs)>8:return {'current':None,'reason':'invalid_glyph_count'}
        digits,masks,aspects,ids,sizes=self.packed[source];result=[];details=[]
        for glyph in glyphs:
            mask=normalize(glyph);aspect=glyph.shape[1]/glyph.shape[0]
            delta=np.abs(np.log(aspect/aspects));inter=np.count_nonzero(masks&mask,axis=(1,2))
            union=sizes+np.count_nonzero(mask)-inter
            scores=1-inter/np.maximum(1,union)+np.minimum(.5,delta)*.25
            scores=np.where(delta>.3,1.,np.minimum(1.,scores))
            best=np.ones(len(digits));np.minimum.at(best,ids,scores)
            ranked=sorted(zip(best.tolist(),digits));first,second=ranked[:2];margin=second[0]-first[0]
            details.append({'digit':first[1],'error':round(first[0],5),'margin':round(margin,5)})
            if first[0]>self.max_error or margin<self.min_margin:return {'current':None,'reason':'glyph_not_distinct','glyphs':details}
            result.append(first[1])
        return {'current':int(''.join(result)),'reason':None,'glyphs':details}
