"""Offline HP/MP OCR benchmark. Python 3.10+, RapidOCR 3.9.x.

Rectangles are x,y,width,height in the ORIGINAL image. Never retain text bounds
between frames. This tool measures OCR, not camera latency or live validation.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np


def rectangle(value):
    try:
        box = tuple(map(int, value.split(',')))
        assert len(box) == 4 and min(box[:2]) >= 0 and min(box[2:]) > 0
        return box
    except (ValueError, AssertionError):
        raise argparse.ArgumentTypeError('Podaj x,y,szerokosc,wysokosc')


def crop_bar(frame, box):
    x, y, w, h = box
    if x + w > frame.shape[1] or y + h > frame.shape[0]:
        raise ValueError('Prostokat wychodzi poza obraz')
    return frame[y:y+h, x:x+w].copy()


def prepare(bar, mode):
    if mode == 'dynamic':
        # Search the WHOLE bar each time. Neutral bright text excludes coloured
        # fill and red annotations. Keep all candidates, including MP suffixes.
        low = bar.min(axis=2).astype(np.int16)
        high = bar.max(axis=2).astype(np.int16)
        mask = ((low >= 140) & (high-low <= 65)).astype(np.uint8)
        mask[[0, -1], :] = 0
        ys, xs = np.where(mask)
        if len(xs):
            x0, x1 = max(0, int(xs.min())-3), min(bar.shape[1], int(xs.max())+4)
            y0, y1 = max(0, int(ys.min())-2), min(bar.shape[0], int(ys.max())+3)
            bar = bar[y0:y1, x0:x1]
        # If no text candidates exist, retain full width rather than guessing.
    bar = cv2.resize(bar, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    pad_y = 96 if mode == 'full' else 6
    return cv2.copyMakeBorder(bar, pad_y, pad_y, 12, 12,
                              cv2.BORDER_CONSTANT, value=(32, 32, 32))


def parse_output(result):
    texts = getattr(result, 'txts', None)
    scores = getattr(result, 'scores', None)
    readings = []
    raw = [] if texts is None else list(texts)
    if scores is None:
        return {'raw': raw, 'value': None}
    for text, score in zip(raw, scores):
        # Accept grouped thousands; do not silently substitute letters for digits.
        clean = re.sub(r'(?<=\d)[ ,.\u00a0](?=\d)', '', text)
        match = re.match(r'^\s*(\d+)\s*/\s*(\d+)(?:\s*\([^)]*\))?\s*$', clean)
        if match and float(score) >= .5:
            current, maximum = map(int, match.groups())
            if maximum > 0 and 0 <= current <= maximum:
                readings.append({'current': current, 'maximum': maximum,
                                 'percent': 100*current/maximum,
                                 'confidence': float(score)})
    return {'raw': raw, 'value': readings[0] if len(readings) == 1 else None}


def worker(args):
    from rapidocr import RapidOCR
    cv2.setNumThreads(1)
    params = {}
    if args.threads > 0:
        params = {'EngineConfig.onnxruntime.intra_op_num_threads': args.threads,
                  'EngineConfig.onnxruntime.inter_op_num_threads': 1}
    engine = RapidOCR(params=params)
    frame = cv2.imdecode(np.fromfile(args.image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError('Nie mozna otworzyc obrazu')
    bars = [crop_bar(frame, args.hp), crop_bar(frame, args.mp)]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    label = f'{args.mode}_threads_{args.threads}'
    for name, bar in zip(('hp', 'mp'), bars):
        cv2.imencode('.png', prepare(bar, args.mode))[1].tofile(output / f'{label}_{name}.png')
    samples, prep_times, ocr_times = [], [], []
    answers = []
    # One unmeasured warmup; a fresh process isolates each thread setting.
    for index in range(args.runs + 1):
        start = time.perf_counter()
        crops = [prepare(bar, args.mode) for bar in bars]
        prepared = time.perf_counter()
        results = [engine(crop, use_det=args.mode == 'full',
                          use_cls=args.mode == 'full', use_rec=True) for crop in crops]
        done = time.perf_counter()
        values = [parse_output(result) for result in results]
        if index:
            samples.append((done-start)*1000)
            prep_times.append((prepared-start)*1000)
            ocr_times.append((done-prepared)*1000)
            answers.append(values)
        print(f'{label}: {index}/{args.runs} {(done-start)*1000:.1f} ms {values}', flush=True)
    report = {'variant': label, 'median_ms': float(np.median(samples)),
              'p95_ms': float(np.percentile(samples, 95)),
              'prepare_median_ms': float(np.median(prep_times)),
              'ocr_median_ms': float(np.median(ocr_times)), 'answers': answers,
              'hp_rect': args.hp, 'mp_rect': args.mp}
    (output / f'{label}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('--hp', type=rectangle, required=True)
    parser.add_argument('--mp', type=rectangle, required=True)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--output', default='ocr_benchmark')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--mode', choices=['full', 'recognition', 'dynamic'], default='full')
    parser.add_argument('--threads', type=int, default=0)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs musi byc >= 1')
    if args.worker:
        worker(args)
        return
    reports = []
    for mode, threads in [('full', 0), ('full', 1), ('recognition', 1),
                          ('dynamic', 1), ('dynamic', 2), ('dynamic', 4)]:
        command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
                   args.image, '--hp', ','.join(map(str, args.hp)),
                   '--mp', ','.join(map(str, args.mp)), '--runs', str(args.runs),
                   '--output', args.output, '--worker', '--mode', mode,
                   '--threads', str(threads)]
        print(f'\nTEST: {mode}, watki={threads or "domyslne"}', flush=True)
        try:
            subprocess.run(command, check=True, timeout=300)
            path = Path(args.output) / f'{mode}_threads_{threads}.json'
            reports.append(json.loads(path.read_text(encoding='utf-8')))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            print(f'Wariant nieudany: {error}', flush=True)
    print('\n--- PODSUMOWANIE (czas pary HP/MP) ---')
    for report in reports:
        print(f'{report["variant"]}: mediana={report["median_ms"]:.1f} ms; '
              f'p95={report["p95_ms"]:.1f} ms; ostatni odczyt={report["answers"][-1]}')
    print('Sprawdz liczby i wycinki PNG. Poprawny format nie dowodzi poprawnego odczytu.')
    if not reports:
        raise RuntimeError('Zaden wariant nie zakonczyl testu')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Przerwano.')
    except Exception as error:
        print(f'BLAD: {error}', file=sys.stderr)
        sys.exit(1)
