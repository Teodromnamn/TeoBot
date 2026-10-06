"""Bounded lossless same-frame samples for replay and independent manual labels."""
import csv
import json
import time
import zipfile
from pathlib import Path

import cv2
from benchmark_hp_mp import crop_bar


class DatasetCapture:
    def __init__(self, folder, hz=5, limit=2000, clock=time.perf_counter):
        if not 0 < hz <= 10 or not 0 < limit <= 2000:
            raise ValueError('Dataset requires 0 < hz <= 10 and 0 < limit <= 2000')
        self.folder = Path(folder)
        self.interval = 1/hz
        self.limit = limit
        self.clock = clock
        self.started = None
        self.last = float('-inf')
        self.count = 0
        self.error = None

    def capture(self, frame, analysis, top_boxes, side_boxes, side_bars):
        now = self.clock()
        if self.error or self.count >= self.limit or now-self.last < self.interval:
            return False
        if self.started is None:
            self.started = now
        case = self.folder / f'case_{self.count:05d}'
        try:
            case.mkdir(parents=True, exist_ok=False)
            for index, resource in enumerate(('hp', 'mp')):
                for kind, boxes in [('top_original', top_boxes),
                                    ('side_original', side_boxes), ('side_bar', side_bars)]:
                    image = crop_bar(frame, boxes[index])
                    ok, encoded = cv2.imencode('.png', image)
                    if not ok:
                        raise OSError('PNG encoding failed')
                    encoded.tofile(case / f'{resource}_{kind}.png')
            step = max(1, side_bars[1][1]-side_bars[0][1])
            x0 = max(0, min(b[0] for b in side_bars)-2*step)
            y0 = max(0, side_bars[0][1]-3*step)
            y1 = min(frame.shape[0], side_bars[1][1]+4*step)
            context_box = (x0,y0,frame.shape[1]-x0,y1-y0)
            ok, encoded = cv2.imencode('.png', crop_bar(frame, context_box))
            if not ok:
                raise OSError('Context PNG encoding failed')
            encoded.tofile(case/'sidebar_context.png')
            meta = {'schema':1, 'elapsed_s':now-self.started,
                    'sampled_at_unix_ms':time.time_ns()//1000000,
                    'frame_shape':list(frame.shape), 'top_rectangles':top_boxes,
                    'side_rectangles':side_boxes, 'side_bar_rectangles':side_bars,
                    'sidebar_context_rectangle':context_box,
                    'analysis':analysis,
                    'note':'Same frame, raw lossless crops. Saved OCR is NOT ground truth. Sample time is analysis time, not game time. Recording changes live latency.'}
            (case/'reading.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        except (OSError, ValueError, cv2.error) as error:
            self.error = str(error)
            print(f'Zapis datasetu wylaczony: {error}', flush=True)
            return False
        self.last = now
        self.count += 1
        return True

    def finish(self):
        if not self.count:
            print('Dataset: brak zapisanych probek.', flush=True)
            return None
        # Empty labels deliberately: previous OCR must not become truth labels.
        with (self.folder/'labels.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['case','hp_current','hp_maximum','mp_current','mp_maximum',
                             'top_occluded','side_occluded','notes'])
            for index in range(self.count):
                writer.writerow([f'case_{index:05d}','','','','','','',''])
        archive = self.folder.with_suffix('.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
            # Exclude incomplete samples after a write failure.
            output.write(self.folder/'labels.csv', 'labels.csv')
            for index in range(self.count):
                for file in sorted((self.folder/f'case_{index:05d}').iterdir()):
                    output.write(file, file.relative_to(self.folder))
        print(f'Wyslij dataset: {archive} ({self.count} probek)', flush=True)
        return archive
