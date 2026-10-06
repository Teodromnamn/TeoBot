"""Replay saved sidebar originals through the current live OCR path, without OBS."""
import argparse
import json
import os
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np
from dual_source import recognize_side
from test_obs_tesseract import Engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--directory', default=r'C:\Program Files\Tesseract-OCR')
    parser.add_argument('--threads', type=int, choices=(1, 2, 4), default=2)
    parser.add_argument('--glyph-retry', action='store_true', help='Retry rejected numbers as separate digits')
    args = parser.parse_args()
    os.environ['OMP_THREAD_LIMIT'] = str(args.threads)
    cv2.setNumThreads(1)
    engine = Engine(args.directory)
    try:
        with zipfile.ZipFile(args.archive) as archive:
            names = sorted(n for n in archive.namelist() if n.endswith('/reading.json'))
            if not names:
                raise ValueError('No conflict cases found in archive')
            print('Saved OCR is not ground truth. Compare new raw text with original images.')
            for name in names:
                folder = name.rsplit('/', 1)[0]
                meta = json.loads(archive.read(name))
                for index, resource in enumerate(('hp', 'mp')):
                    data = archive.read(f'{folder}/{resource}_side_original.png')
                    crop = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if crop is None:
                        raise ValueError(f'Cannot decode {folder}/{resource}')
                    start = time.perf_counter()
                    result = recognize_side(engine, crop, glyph_retry=args.glyph_retry)
                    elapsed = (time.perf_counter()-start)*1000
                    saved = meta['analysis']['readings'][index]
                    print(json.dumps({'case':folder, 'resource':resource,
                                      'old_side':saved.get('side', {}).get('raw'),
                                      'new_side':result['raw'], 'current':result['current'],
                                      'visible_digit_groups':result['visible_digit_groups'],
                                      'reason':result.get('reason'), 'glyph_recovery':result.get('glyph_recovery'), 'saved_top':saved.get('raw'),
                                      'ms':round(elapsed, 2)}, ensure_ascii=False))
    finally:
        engine.tess.close()


if __name__ == '__main__':
    main()
