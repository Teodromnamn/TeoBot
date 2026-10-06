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
from dual_source import recognize_side, ConfirmationGate
from test_obs_tesseract import Engine, binary, recognize_top
from source_selection import select_source,needs_glyph_check,corroborate_top
from test_obs_pipeline import ConfirmMaximum
from bar_fill import FillEvidence, validate_fill


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('--labels',type=Path,help='Independently filled labels.csv; blank cells are skipped')
    p.add_argument('--directory',default=r'C:\Program Files\Tesseract-OCR')
    p.add_argument('--threads',type=int,choices=(1,2,4),default=2)
    p.add_argument('--color-check',action='store_true',help='Validate OCR percentage against calibrated fill intervals')
    p.add_argument('--resilient-verification',action='store_true',help='Glyph retries, source arbitration and temporal confirmation; implies color-check')
    p.add_argument('--saved-ocr',type=Path,help='Reuse top/side observations from a prior replay JSONL; no Tesseract rerun. Not labels.')
    args = p.parse_args()
    args.color_check = args.color_check or args.resilient_verification
    saved = {}
    if args.saved_ocr:
        with args.saved_ocr.open(encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip():continue
                row=json.loads(line)
                if 'case' not in row:continue
                key=(row['case'],row['resource'])
                if key in saved:raise ValueError('Duplicate saved OCR observation')
                saved[key]=row
        if not saved:raise ValueError('No saved OCR observations')
    labels = {}
    if args.labels:
        with args.labels.open(encoding='utf-8-sig',newline='') as f:
            labels = {row['case']:row for row in csv.DictReader(f)}
    os.environ['OMP_THREAD_LIMIT'] = str(args.threads)
    cv2.setNumThreads(1)
    engine = None if args.saved_ocr else Engine(args.directory)
    stats = Counter()
    try:
        with zipfile.ZipFile(args.archive) as archive:
            cases = sorted(n.rsplit('/',1)[0] for n in archive.namelist() if n.endswith('/reading.json'))
            if not cases:
                raise ValueError('No dataset samples')
            if saved and set(saved) != {(case,r) for case in cases for r in ('hp','mp')}:
                raise ValueError('Saved OCR case IDs/resources do not match this archive')
            reference = 'calibration' if 'calibration/hp_top_original.png' in archive.namelist() else cases[0]
            models = {}
            if args.color_check:
                for resource in ('hp','mp'):
                    models[resource] = {}
                    for kind in ('top_original','side_bar'):
                        data=np.frombuffer(archive.read(f'{reference}/{resource}_{kind}.png'),np.uint8)
                        model_image=cv2.imdecode(data,cv2.IMREAD_COLOR)
                        models[resource][kind]=FillEvidence(model_image,resource,sidebar=kind=='side_bar')
            gates = {r:ConfirmationGate(allow_color_supported=True) for r in ('hp','mp')}
            maximum_guards = {}
            if args.resilient_verification:
                for resource in ('hp','mp'):
                    def reference_image(kind):
                        return cv2.imdecode(np.frombuffer(archive.read(f'{reference}/{resource}_{kind}.png'),np.uint8),1)
                    ref = saved[(cases[0],resource)]['top'] if saved else recognize_top(engine,binary(prepare(reference_image('top_original'),'dynamic')))
                    # Calibration PNGs do not include counters; use full top ratios.
                    value = ref['value']
                    if value is None or value['current'] != value['maximum']:
                        raise ValueError('Resilient replay requires a verified full calibration frame')
                    maximum_guards[resource] = ConfirmMaximum(value['maximum'])
            for case in cases:
                metadata = json.loads(archive.read(f'{case}/reading.json'))
                observed_at = float(metadata['elapsed_s'])

                for resource in ('hp','mp'):
                    def image(kind):
                        data = np.frombuffer(archive.read(f'{case}/{resource}_{kind}.png'),np.uint8)
                        result = cv2.imdecode(data,cv2.IMREAD_COLOR)
                        if result is None:
                            raise ValueError(f'Invalid image: {case}/{resource}/{kind}')
                        return result
                    start = time.perf_counter()
                    if saved:
                        top = saved[(case,resource)]['top']
                        side = saved[(case,resource)]['side']
                    else:
                        top = recognize_top(engine,binary(prepare(image('top_original'),'dynamic')),args.resilient_verification)
                        side = recognize_side(engine,image('side_original'),args.resilient_verification)
                    value = top['value']
                    agreement = value is not None and side['current'] == value['current']
                    checked = None
                    if args.color_check:
                        checked=validate_fill(top,{kind:model.measure(image(kind))
                                                  for kind,model in models[resource].items()})
                        stats['color_consistent'] += int(checked.get('fill_status')=='consistent')
                        stats['color_conflicts'] += int(checked.get('fill_status')=='conflict')
                    stats['top_glyph_recovered'] += int(top.get('method') == 'visual_separator_and_glyphs')
                    stats['side_glyph_recovered'] += int(side.get('method') == 'separate_glyphs')
                    stats['resource_samples'] += 1
                    stats['source_agreements'] += int(agreement)
                    selected = confirmed = None
                    if args.resilient_verification:
                        evidence = {('top' if kind=='top_original' else 'sidebar'):e
                                    for kind,e in checked['fill'].items()}
                        guard = maximum_guards[resource]
                        if needs_glyph_check(top,side,evidence,guard.maximum):
                            if engine is None:engine=Engine(args.directory)
                            top=corroborate_top(engine,top,binary(prepare(image('top_original'),'dynamic')))
                        selected = select_source(top,side,evidence,guard.maximum)
                        confirmed = gates[resource].apply(selected,observed_at)
                        maximum_status = guard.update(confirmed['value'])
                        if maximum_status == 'maximum_pending':
                            confirmed = dict(confirmed,candidate_value=confirmed['value'],value=None,
                                             quality='unconfirmed',confirmation='maximum_pending')
                        if confirmed.get('confirmation_reset_reason'):
                            stats['wait_'+confirmed['confirmation_reset_reason']] += 1
                        stats['selected_resources'] += int(selected['value'] is not None)
                        stats['confirmed_resources'] += int(confirmed['value'] is not None)
                        stats['single_source_selected'] += int(selected.get('verification') in ('top_color_supported','side_color_supported','top_glyphs_supported_without_color'))
                    row = labels.get(case,{})
                    truth = [row.get(resource+'_current',''),row.get(resource+'_maximum','')]
                    correct = None
                    color_accepted = agreement and checked is not None and checked.get('value') is not None
                    if truth[0].strip():
                        current=int(truth[0]);maximum=int(truth[1]) if truth[1].strip() else None
                        stats['manually_labeled'] += 1
                        if selected is not None and selected['value'] is not None:
                            stats['labeled_selected'] += 1
                            stats['wrong_labeled_selected_current'] += int(selected['value']['current'] != current)
                        if confirmed is not None and confirmed['value'] is not None:
                            cv = confirmed['value']
                            stats['labeled_confirmed'] += 1
                            stats['wrong_labeled_confirmed_current'] += int(cv['current'] != current)
                            if maximum is not None and cv.get('maximum') is not None:
                                stats['labeled_confirmed_maximum'] += 1
                                stats['wrong_labeled_confirmed_maximum'] += int(cv['maximum'] != maximum)
                        if agreement:
                            correct = value['current']==current and (maximum is None or value['maximum']==maximum)
                            stats['labeled_agreements'] += 1
                            stats['correct_labeled_agreements'] += int(correct)
                            stats['wrong_labeled_agreements'] += int(not correct)
                            if color_accepted:
                                stats['labeled_color_accepted'] += 1
                                stats['wrong_labeled_color_accepted'] += int(not correct)
                    print(json.dumps({'case':case,'resource':resource,'top':top,'side':side,
                                      'agreement':agreement,'correct_against_manual_label':correct,
                                      'color':checked,'selected':selected,'confirmed':confirmed,
                                      'ocr_reused':bool(saved),
                                      'color_accepted':color_accepted if args.color_check else None,
                                      'ms':round((time.perf_counter()-start)*1000,2)}))
        print(json.dumps({'summary':dict(stats),'note':('Agreement is not accuracy. Temporal replay uses recorded sample times, not every live frame; camera age and actions are not simulated.' if args.resilient_verification else 'Agreement is not accuracy; no action or temporal confirmation simulated.')}))
    finally:
        if engine is not None:engine.tess.close()


if __name__ == '__main__':
    main()
