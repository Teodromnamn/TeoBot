"""Replay raw dataset crops. Manual labels are optional; stored OCR is not truth."""
import argparse
import csv
import json
import os
import time
import zipfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from benchmark_hp_mp import prepare
from dual_source import recognize_side
from test_obs_tesseract import Engine, binary, parse_reading
from bar_fill import FillEvidence, validate_fill


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('--labels',type=Path,help='Independently filled labels.csv; blank cells are skipped')
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
    p.add_argument('--threads',type=int,choices=(1,2,4),default=2)
    p.add_argument('--color-check',action='store_true',help='Validate OCR percentage against calibrated fill intervals')
    args = p.parse_args()
    labels = {}
    if args.labels:
        with args.labels.open(encoding='utf-8-sig',newline='') as f:
            labels = {row['case']:row for row in csv.DictReader(f)}
    os.environ['OMP_THREAD_LIMIT'] = str(args.threads)
    cv2.setNumThreads(1)
    engine = Engine(args.directory)
    stats = Counter()
    try:
        with zipfile.ZipFile(args.archive) as archive:
            cases = sorted(n.rsplit('/',1)[0] for n in archive.namelist() if n.endswith('/reading.json'))
            if not cases:
                raise ValueError('No dataset samples')
            reference = 'calibration' if 'calibration/hp_top_original.png' in archive.namelist() else cases[0]
            models = {}
            if args.color_check:
                for resource in ('hp','mp'):
                    models[resource] = {}
                    for kind in ('top_original','side_bar'):
                        data=np.frombuffer(archive.read(f'{reference}/{resource}_{kind}.png'),np.uint8)
                        model_image=cv2.imdecode(data,cv2.IMREAD_COLOR)
                        models[resource][kind]=FillEvidence(model_image,resource,sidebar=kind=='side_bar')
            for case in cases:
                for resource in ('hp','mp'):
                    def image(kind):
                        data = np.frombuffer(archive.read(f'{case}/{resource}_{kind}.png'),np.uint8)
                        result = cv2.imdecode(data,cv2.IMREAD_COLOR)
                        if result is None:
                            raise ValueError(f'Invalid image: {case}/{resource}/{kind}')
                        return result
                    start = time.perf_counter()
                    top = parse_reading(engine.recognize(binary(prepare(image('top_original'),'dynamic'))))
                    side = recognize_side(engine,image('side_original'))
                    value = top['value']
                    agreement = value is not None and side['current'] == value['current']
                    checked = None
                    if args.color_check:
                        checked=validate_fill(top,{kind:model.measure(image(kind))
                                                  for kind,model in models[resource].items()})
                        stats['color_consistent'] += int(checked.get('fill_status')=='consistent')
                        stats['color_conflicts'] += int(checked.get('fill_status')=='conflict')
                    stats['resource_samples'] += 1
                    stats['source_agreements'] += int(agreement)
                    row = labels.get(case,{})
                    truth = [row.get(resource+'_current',''),row.get(resource+'_maximum','')]
                    correct = None
                    color_accepted = agreement and checked is not None and checked.get('value') is not None
                    if all(v.strip() for v in truth):
                        current, maximum = map(int,truth)
                        stats['manually_labeled'] += 1
                        if agreement:
                            correct = value['current']==current and value['maximum']==maximum
                            stats['labeled_agreements'] += 1
                            stats['correct_labeled_agreements'] += int(correct)
                            stats['wrong_labeled_agreements'] += int(not correct)
                            if color_accepted:
                                stats['labeled_color_accepted'] += 1
                                stats['wrong_labeled_color_accepted'] += int(not correct)
                    print(json.dumps({'case':case,'resource':resource,'top':top,'side':side,
                                      'agreement':agreement,'correct_against_manual_label':correct,
                                      'color':checked,
                                      'color_accepted':color_accepted if args.color_check else None,
                                      'ms':round((time.perf_counter()-start)*1000,2)}))
        print(json.dumps({'summary':dict(stats),'note':'Agreement is not accuracy; no action or temporal confirmation simulated.'}))
    finally:
        engine.tess.close()


if __name__ == '__main__':
    main()
