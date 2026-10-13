"""Exact output equivalence and alternating-order timing on unique native rasters."""
import argparse,hashlib,json,time,zipfile
from pathlib import Path
import cv2,numpy as np
from template_counter import TemplateCounter
from vectorized_template_counter import VectorizedTemplateCounter

def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('--output',type=Path,default=Path('vectorized_results.json'));a=p.parse_args();cv2.setNumThreads(1)
    model=json.loads(Path(__file__).with_name('counter_templates_v1.json').read_text());old=TemplateCounter(model);new=VectorizedTemplateCounter(model);rasters={};occurrences=0
    for spec in json.loads(a.manifest.read_text()):
        z=zipfile.ZipFile(spec['archive']) if 'archive' in spec else None
        if z:
            names=[n for n in z.namelist() if n.endswith(('_top_original.png','_side_original.png'))]
            entries=((n,z.read(n)) for n in names)
        else:
            entries=((str(f),f.read_bytes()) for f in Path(spec['directory']).glob('case_*/*_original.png') if int(f.parent.name.split('_')[-1])>=spec.get('start',0))
        for n,data in entries:
            source='top' if n.endswith('_top_original.png') else 'side';im=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
            key=source+str(im.shape)+hashlib.sha256(im.tobytes()).hexdigest();rasters[key]=(source,im);occurrences+=1
        if z:z.close()
    errors=[];times={'old':[],'vectorized':[]};counts={'old':0,'vectorized':0}
    for index,(key,(source,im)) in enumerate(sorted(rasters.items())):
        outputs={}
        for name,reader in ([('old',old),('vectorized',new)] if index%2 else [('vectorized',new),('old',old)]):
            t=time.perf_counter();out=reader.read(im,source);times[name].append((time.perf_counter()-t)*1000);outputs[name]=out
            counts[name]+=int(out['current'] is not None)
        if outputs['old']!=outputs['vectorized']:errors.append({'key':key,'old':outputs['old'],'vectorized':outputs['vectorized']})
    result={'passed':not errors,'raw_crop_occurrences':occurrences,'unique_source_rasters':len(rasters),'accepted':counts,'errors':errors[:20],'error_count':len(errors),'timing_ms':{n:{'median':float(np.median(ts)),'p95':float(np.percentile(ts,95)),'total':sum(ts)} for n,ts in times.items()},'note':'All raw rasters including occlusions. Exact dictionary equality (values, rejection reasons, glyph errors and margins). Alternating measurement order, one OpenCV thread; no OCR, OBS, publication or actions.'}
    a.output.write_text(json.dumps(result,indent=2));print(json.dumps(result));return int(bool(errors))
if __name__=='__main__':raise SystemExit(main())
