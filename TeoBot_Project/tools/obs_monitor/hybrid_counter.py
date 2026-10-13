"""Experimental current candidates: strict font templates, then resident OCR.

Does not arbitrate sources, confirm readings, update maxima or execute actions.
"""
from benchmark_template_counter import valid_crop
from benchmark_hp_mp import prepare
from test_obs_tesseract import binary,recognize_top
from dual_source import recognize_side


class HybridCounter:
    def __init__(self,templates,engine):
        self.templates=templates;self.engine=engine
        self.counts={'template_accepted':0,'fallback_attempts':0,'fallback_numeric_results':0,'occluded':0}

    def read(self,crop,source,resource):
        if source not in ('top','side') or resource not in ('hp','mp'):
            raise ValueError('Unknown counter source/resource')
        if not valid_crop(crop,source,resource):
            self.counts['occluded']+=1
            return {'current':None,'reason':'occlusion_filter','method':'unavailable'}
        initial=self.templates.read(crop,source)
        if initial['current'] is not None:
            self.counts['template_accepted']+=1
            return dict(initial,method='native_template')
        self.counts['fallback_attempts']+=1
        if source=='top':
            recovered=recognize_top(self.engine,binary(prepare(crop,'dynamic')),True,raw_crop=crop,resource=resource)
            value=(recovered.get('value') or {}).get('current')
        else:
            recovered=recognize_side(self.engine,crop,True)
            value=recovered.get('current')
        if value is not None:self.counts['fallback_numeric_results']+=1
        return {'current':value,'reason':None if value is not None else 'template_and_ocr_unavailable',
                'method':'tesseract_fallback','template_rejection':initial,'ocr':recovered}
