"""Bounded, opt-in diagnostics. Saves crops only, never the full game frame."""
import json
import time
import zipfile
from pathlib import Path

import cv2
from benchmark_hp_mp import crop_bar, prepare
from dual_source import side_image


def diagnostic_needed(reading):
    return (reading.get('verification') == 'conflict' or
            reading.get('fill_status') in ('conflict','unavailable') or
            (reading.get('side') or {}).get('reason') in ('digit_count_mismatch','foreign_color_overlay') or
            ('value' in reading and reading['value'] is None and
             reading.get('confirmation') != 'waiting_second_frame'))


class ConflictCapture:
    def __init__(self, folder, limit=60, clock=time.perf_counter):
        self.folder = Path(folder)
        self.limit = limit
        self.clock = clock
        self.started = clock()
        self.last = float('-inf')
        self.seen = {}
        self.count = 0
        self.error = None

    def capture(self, frame, analysis, top_boxes, side_boxes, binary, side_bar_boxes=None):
        now = self.clock()
        readings = analysis['readings']
        if not any(diagnostic_needed(r) for r in readings):
            return False
        if self.error or self.count >= self.limit or now-self.last < .5:
            return False
        # Two examples of each raw disagreement, at least five seconds apart.
        signature = json.dumps([(i, r.get('raw'), (r.get('side') or {}).get('raw'), r.get('confirmation'), r.get('reason'))
                                for i,r in enumerate(readings)
                                if diagnostic_needed(r)], sort_keys=True)
        occurrences, last = self.seen.get(signature, (0, float('-inf')))
        if occurrences >= 2 or now-last < 5:
            return False
        case = self.folder / f'case_{self.count:03d}'
        try:
            case.mkdir(parents=True, exist_ok=False)
            for index, resource in enumerate(('hp', 'mp')):
                top = crop_bar(frame, top_boxes[index])
                prepared = prepare(top, 'dynamic')
                side = crop_bar(frame, side_boxes[index])
                images = {'top_original':top, 'top_prepared':prepared,
                          'top_binary':binary(prepared), 'side_original':side,
                          'side_binary':side_image(side)}
                if side_bar_boxes is not None:
                    images['side_bar'] = crop_bar(frame, side_bar_boxes[index])
                for name, image in images.items():
                    ok, encoded = cv2.imencode('.png', image)
                    if not ok:
                        raise OSError('PNG encoding failed')
                    encoded.tofile(case/f'{resource}_{name}.png')
            metadata = {'saved_at_unix_ms':time.time_ns()//1000000,
                        'elapsed_s':now-self.started, 'frame_shape':list(frame.shape),
                        'top_rectangles':top_boxes, 'side_rectangles':side_boxes,
                        'side_bar_rectangles':side_bar_boxes,
                        'analysis':analysis,
                        'side_preprocessing':'tight_cubic4_threshold120_border16_psm8_digit_count',
                        'note':'Both sources from one analyzed frame. Preprocessing replayed deterministically; no extra OCR. Readings are not ground-truth labels.'}
            (case/'reading.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        except (OSError, ValueError, cv2.error) as error:
            self.error = str(error)
            print(f'Diagnostyka wylaczona po bledzie zapisu: {error}', flush=True)
            return False
        self.count += 1
        self.last = now
        self.seen[signature] = (occurrences+1, now)
        return True

    def finish(self):
        if not self.count:
            print('Diagnostyka: brak zapisanych konfliktow.', flush=True)
            return None
        path = self.folder.with_suffix('.zip')
        try:
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(self.folder.rglob('*')):
                    if file.is_file():
                        archive.write(file, file.relative_to(self.folder))
            print(f'Wyslij paczke konfliktow: {path} ({self.count} przypadkow)', flush=True)
            return path
        except OSError as error:
            print(f'Nie mozna utworzyc ZIP: {error}. Wycinki pozostaja w {self.folder}', flush=True)
            return None
