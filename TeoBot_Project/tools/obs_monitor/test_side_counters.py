"""Offline sidebar OCR diagnostic. Pass full-HP/MP image first, then more images.

No live fallback is enabled by this diagnostic. Inspect numbers, not just syntax.
"""
import argparse
import json
import os
import re
import time
from pathlib import Path

import cv2
import numpy as np
from test_tesseract_resident import ResidentTesseract


def locate(frame, return_bars=False):
    """Find aligned full red/blue bars in the right quarter; reject ambiguity."""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue, sat, val = cv2.split(hsv)
    masks = [((hue < 12) | (hue > 165)), ((hue > 95) & (hue < 135))]
    groups = []
    for mask in masks:
        mask = (mask & (sat > 100) & (val > 90)).astype('uint8')
        mask[:int(h*.08)] = 0
        mask[:, :int(w*.75)] = 0
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        groups.append([tuple(map(int, s[:4])) for s in stats[1:]
                       if s[2] >= w*.025 and 3 <= s[3] <= h*.03
                       and s[2]/s[3] >= 4 and s[4]/(s[2]*s[3]) > .5])
    pairs = []
    for red in groups[0]:
        for blue in groups[1]:
            x, y, bw, bh = red
            bx, by, bwidth, bheight = blue
            if (abs(x-bx) <= bh and .8 <= bw/bwidth <= 1.25
                    and .7*bh <= by-y <= 2*max(bh,bheight)):
                pairs.append((red, blue))
    if len(pairs) != 1:
        raise ValueError(f'Expected one full sidebar pair, found {len(pairs)}')
    red, blue = pairs[0]
    step = blue[1]-red[1]
    right = max(red[0]+red[2], blue[0]+blue[2])
    # Keep all space to the panel edge, not a fixed number of digits.
    left = right+max(2, round(step*.3))
    boxes = [(left, y-2, w-left-2, step+1) for y in (red[1], blue[1])]
    return (boxes, (red, blue)) if return_bars else boxes


def variants(crop):
    gray = crop.min(axis=2)
    large = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    images = {'gray': 255-large}
    for threshold in (80, 100, 120):
        images[f'threshold_{threshold}'] = np.where(large > threshold, 0, 255).astype('uint8')
    return {name: cv2.copyMakeBorder(im, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
            for name, im in images.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--directory', default=r'C:\Program Files\Tesseract-OCR')
    parser.add_argument('--output', type=Path, default=Path('sidebar_results'))
    args = parser.parse_args()
    os.environ['OMP_THREAD_LIMIT'] = '2'
    cv2.setNumThreads(1)
    output = args.output / time.strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True, exist_ok=True)
    engine = ResidentTesseract(args.directory)
    rows = []
    boxes, shape = None, None
    try:
        for index, path in enumerate(args.images):
            frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError(f'Cannot read {path}')
            if boxes is None:
                boxes, shape = locate(frame), frame.shape
            if frame.shape != shape:
                raise ValueError('Images must use the same layout and resolution as the first image')
            annotated = frame.copy()
            for resource, (x,y,w,h) in zip(('hp','mp'), boxes):
                if min(x,y,w,h) < 0 or y+h > frame.shape[0] or w == 0 or h == 0:
                    raise ValueError('Invalid sidebar rectangle')
                crop = frame[y:y+h,x:x+w]
                cv2.rectangle(annotated,(x,y),(x+w-1,y+h-1),(0,0,255),1)
                for variant, image in variants(crop).items():
                    start = time.perf_counter()
                    text = engine.read(image)
                    ms = (time.perf_counter()-start)*1000
                    row = {'image':str(path),'resource':resource,'variant':variant,
                           'raw':text,'current':int(text) if re.fullmatch(r'[0-9]+',text) else None,
                           'ms':ms,'rectangle':[x,y,w,h]}
                    rows.append(row)
                    print(json.dumps(row, ensure_ascii=True))
                    cv2.imencode('.png',image)[1].tofile(output/f'{index}_{resource}_{variant}.png')
            cv2.imencode('.png',annotated)[1].tofile(output/f'{index}_areas.png')
    finally:
        engine.close()
    (output/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print(f'Results: {output}. Numeric format does NOT prove accuracy.')


if __name__ == '__main__':
    main()
