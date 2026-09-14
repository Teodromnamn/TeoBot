"""Live OBS Auto benchmark; place beside benchmark_hp_mp.py in project/tools.

One latest-frame slot, fresh text bounds per read, no input automation.
Time measurements start at camera reception, not at rendering in the game.
"""
import argparse
import csv
import json
import gc
import os
import platform
import hashlib
from importlib.metadata import version
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from benchmark_hp_mp import crop_bar, prepare, parse_output
from test_obs_marker import Detector, Health
from vision_analyzers import HpMpAnalyzer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class Camera:
    def __init__(self, args):
        self.args = args
        self.condition = threading.Condition()
        self.stop = threading.Event()
        self.latest = None
        self.error = None
        self.count = 0
        self.marked = None
        self.detector, self.health = Detector(), Health()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        cap = None
        try:
            from cv2_enumerate_cameras import enumerate_cameras
            devices = list(enumerate_cameras(cv2.CAP_DSHOW))
            matches = [c for c in devices if c.name.strip().casefold() == 'obs virtual camera']
            if len(matches) != 1:
                raise RuntimeError(f'Oczekiwano jednej OBS Virtual Camera; znaleziono {len(matches)}. '
                                   f'Urzadzenia: {[c.name for c in devices]}')
            device = matches[0]
            cap = cv2.VideoCapture(device.index, device.backend)
            if not cap.isOpened():
                raise RuntimeError('Nie mozna otworzyc kamery OBS')
            for prop, value in [(cv2.CAP_PROP_FRAME_WIDTH, self.args.width),
                                (cv2.CAP_PROP_FRAME_HEIGHT, self.args.height),
                                (cv2.CAP_PROP_FPS, self.args.fps)]:
                cap.set(prop, value)
            shape = None
            while not self.stop.is_set():
                ok, frame = cap.read()
                received = time.perf_counter()
                wall_ms = time.time_ns() // 1000000
                if not ok or frame is None:
                    raise RuntimeError('Brak klatki z kamery')
                if shape is None:
                    shape = frame.shape
                    print(f'OBS: {shape[1]}x{shape[0]}, indeks={device.index}', flush=True)
                elif frame.shape != shape:
                    raise RuntimeError('Rozdzielczosc zmieniona. Uruchom test i kalibracje ponownie.')
                with self.condition:
                    self.count += 1
                    self.latest = (self.count, received, frame)
                    self.marked = (self.count, received, frame, wall_ms)
                    self.condition.notify_all()
        except Exception as error:
            with self.condition:
                self.error = str(error)
                self.condition.notify_all()
        finally:
            if cap is not None:
                cap.release()

    def get(self, after=0):
        with self.condition:
            ready = self.condition.wait_for(
                lambda: self.error or (self.latest is not None and self.latest[0] > after), 10)
            if self.error:
                raise RuntimeError(self.error)
            if not ready:
                raise RuntimeError('Brak nowej klatki przez 10 sekund')
            return self.latest

    def get_marked(self, after):
        with self.condition:
            self.condition.wait_for(lambda: self.error or (self.marked is not None and self.marked[0] > after), .25)
            if self.error:
                raise RuntimeError(self.error)
            item = self.marked if self.marked is not None and self.marked[0] > after else None
        if item is None:
            return None
        seq, received, frame, wall_ms = item
        start = time.perf_counter()
        stamp = self.detector.read(frame, start)
        status, age = self.health.update(stamp, wall_ms, received, self.args.max_age_ms)
        self.marker_ms = (time.perf_counter()-start)*1000
        return seq, received, frame, stamp, status, age


def result_status(marker_status, age, elapsed_ms, statuses):
    if marker_status != 'OK':
        return marker_status
    if age is None or age < 0:
        return 'ZEGAR_NIEZGODNY'
    if any(s == 'unreadable' for s in statuses):
        return 'BRAK_ODCZYTU'
    if any(s == 'maximum_pending' for s in statuses):
        return 'POTWIERDZANIE_MAKSIMUM'
    return 'OK'


def publish(path, status, readings=None, age_ms=None, max_age_ms=250, bar_statuses=None):
    """Publish each resource independently; retain history without refreshing it."""
    now_ms = time.time_ns() // 1000000
    fresh = (status in ('OK', 'BRAK_ODCZYTU', 'POTWIERDZANIE_MAKSIMUM')
             and age_ms is not None and 0 <= age_ms <= max_age_ms)
    previous = {}
    try:
        previous = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    data = {'schema': 2, 'status': status, 'published_at_unix_ms': now_ms,
            'result_age_ms': age_ms}
    resources = {}
    for index, name in enumerate(('hp', 'mp')):
        reading = readings[index] if readings else {}
        value = reading.get('value')
        accepted = (bar_statuses is None or bar_statuses[index] in ('ok', 'maximum_changed'))
        valid = fresh and accepted and value is not None
        old = previous.get('resources', {}).get(name, {})
        last_known = old.get('last_known')
        expires = now_ms + max(0, max_age_ms-age_ms) if valid else now_ms
        if valid:
            last_known = {'value': value, 'source': 'top_text',
                          'observed_at_unix_ms': now_ms-age_ms,
                          'expires_at_unix_ms': expires}
        resources[name] = {
            'valid': valid, 'quality': 'exact' if valid else ('stale' if last_known else 'unavailable'),
            'source': 'top_text' if valid else None,
            'value': value if valid else None,
            'reason': (bar_statuses[index] if fresh and bar_statuses else status),
            'observed_at_unix_ms': now_ms-age_ms if valid else None,
            'expires_at_unix_ms': expires,
            'last_known': last_known}
        data[name] = value if valid else None
    data['resources'] = resources
    data['valid'] = all(r['valid'] for r in resources.values())
    data['expires_at_unix_ms'] = min(r['expires_at_unix_ms'] for r in resources.values())
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(path)


class ConfirmMaximum:
    """Require two consecutive valid readings before accepting a new maximum."""
    def __init__(self, initial):
        self.maximum = initial
        self.pending = None
        self.count = 0

    def update(self, value):
        if value is None:
            self.pending, self.count = None, 0
            return 'unreadable'
        maximum = value['maximum']
        if maximum == self.maximum:
            self.pending, self.count = None, 0
            return 'ok'
        self.count = self.count + 1 if self.pending == maximum else 1
        self.pending = maximum
        if self.count >= 2:
            self.maximum = maximum
            self.pending, self.count = None, 0
            return 'maximum_changed'
        return 'maximum_pending'


def read_pair(engine, frame, pair):
    return [parse_output(engine(prepare(crop_bar(frame, rect), 'dynamic'),
                                use_det=False, use_cls=False, use_rec=True)) for rect in pair]


def stats(values):
    return {'median': float(np.median(values)), 'p95': float(np.percentile(values, 95)),
            'max': float(max(values))} if values else None


def make_engine(threads):
    from rapidocr import RapidOCR
    return RapidOCR(params={
        'EngineConfig.onnxruntime.intra_op_num_threads': threads,
        'EngineConfig.onnxruntime.inter_op_num_threads': 1})


def choose_variant(reports, baseline):
    eligible = [r for r in reports if r['samples'] >= 4 and r['valid_fraction'] >= .9]
    if not eligible:
        raise RuntimeError('Auto: za malo czytelnych odczytow. Sprawdz obraz i ponow test.')
    for r in eligible:
        # Penalize capture degradation; camera FPS does not measure game FPS.
        r['score'] = r['p95_ms'] * max(1., baseline / max(1., r['camera_fps']))
    best = min(r['score'] for r in eligible)
    return min((r for r in eligible if r['score'] <= best * 1.10),
               key=lambda r: r['threads'])['threads']


def tune(camera, pair, baseline):
    candidates = [n for n in (1, 2, 4) if n <= (os.cpu_count() or 1)]
    collected = {n: {'times': [], 'valid': 0, 'frames': 0, 'duration': 0.} for n in candidates}
    print('AUTO: dwie rundy w odwrotnej kolejnosci, po 3 s na wariant + rozgrzewka. Graj normalnie.', flush=True)
    for threads in candidates + list(reversed(candidates)):
        engine = make_engine(threads)
        try:
            seq, _, frame = camera.get()
            read_pair(engine, frame, pair)  # warmup, excluded
            first, _, _ = camera.get()
            seq = first
            start = time.perf_counter()
            data = collected[threads]
            while time.perf_counter()-start < 3:
                seq, _, frame = camera.get(seq)
                begin = time.perf_counter()
                result = read_pair(engine, frame, pair)
                data['times'].append((time.perf_counter()-begin)*1000)
                data['valid'] += int(all(r['value'] is not None for r in result))
            elapsed = time.perf_counter()-start
            with camera.condition:
                data['frames'] += camera.count-first
            data['duration'] += elapsed
            print(f'AUTO: zakonczono {threads} watkow', flush=True)
        finally:
            del engine
            gc.collect()
    reports = [{'threads': n, 'samples': len(d['times']),
                'valid_fraction': d['valid']/len(d['times']),
                'p95_ms': float(np.percentile(d['times'], 95)),
                'camera_fps': d['frames']/d['duration']} for n, d in collected.items()]
    selected = choose_variant(reports, baseline)
    print('AUTO wyniki: ' + json.dumps(reports, indent=2))
    return selected, reports


def cache_key(frame, pair, args):
    # Invalidate when hardware, software, OCR helpers, output or crop sizes change.
    description = {'schema': 1, 'host': platform.node(), 'cpu': platform.processor(),
                   'cpus': os.cpu_count(), 'platform': platform.platform(),
                   'shape': list(frame.shape), 'bars': [list(r[2:]) for r in pair],
                   'fps': args.fps, 'target': args.target_fps,
                   'rapidocr': version('rapidocr'), 'onnxruntime': version('onnxruntime'),
                   'helper': hashlib.sha256(Path(__file__).with_name('benchmark_hp_mp.py').read_bytes()).hexdigest()}
    return description


def cached_threads(path, key):
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        n = saved['threads']
        if saved['key'] == key and n in (1, 2, 4) and n <= (os.cpu_count() or 1):
            return n
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--threads', choices=['auto', '1', '2', '4'], default='auto')
    parser.add_argument('--target-fps', type=float, default=10, help='Docelowa liczba odczytow pary na sekunde')
    parser.add_argument('--retune', action='store_true', help='Ponow test Auto zamiast uzywac pamieci')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--fps', type=int, default=60)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--max-age-ms', type=int, default=250,
                        help='Maksymalny wiek wyniku liczony od znacznika OBS')
    args = parser.parse_args()
    if not np.isfinite(args.target_fps) or min(args.seconds, args.width, args.height, args.fps, args.target_fps, args.max_age_ms) <= 0:
        parser.error('Parametry liczbowe musza byc dodatnie')
    from rapidocr import RapidOCR
    from game.status_bar_detector import _tibia_top_pair
    cv2.setNumThreads(1)
    engine = make_engine(1)  # calibration only; release before tuning
    output = Path('obs_fast_results') / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + f'_t{args.threads}')
    output.mkdir(parents=True)
    camera = Camera(args)
    camera.thread.start()
    rows = []
    events = []
    latest_path = output / 'latest.json'
    publish(latest_path, 'URUCHAMIANIE')
    try:
        camera.get()
        print('Rozgrzewka 3 s...', flush=True)
        time.sleep(3)
        first, begin, _ = camera.get()
        baseline_start = time.perf_counter()
        time.sleep(10)
        last, _, _ = camera.get(first)
        baseline = (last-first)/(time.perf_counter()-baseline_start)
        print(f'Odbior bez OCR: {baseline:.2f} FPS')
        while True:
            input('Uruchom kamere OBS, pokaz gre i pelne HP/MP. ENTER: kalibracja. ')
            seq, _, _ = camera.get()
            ready_marker = camera.get_marked(seq)
            if ready_marker is None or ready_marker[4] != 'OK':
                print('Kalibracja: brak swiezego znacznika. Pokaz obs_marker.html w scenie OBS.')
                continue
            seq, _, frame, _, _, _ = ready_marker
            pair = _tibia_top_pair(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if pair is None:
                print('Brak gornych paskow. Sprawdz scene OBS i kamere. Samo urzadzenie nie potwierdza transmisji gry.')
                continue
            readings = read_pair(engine, frame, pair)
            values = [r['value'] for r in readings]
            if any(v is None or v['current'] != v['maximum'] for v in values):
                print(f'Kalibracja wymaga czytelnych, pelnych HP i MP: {readings}')
                continue
            annotated = frame.copy()
            for name, rect in zip(['HP', 'MP'], pair):
                x, y, w, h = rect
                cv2.rectangle(annotated, (x, y), (x+w-1, y+h-1), (0, 0, 255), 1)
                print(name, rect)
            cv2.imencode('.png', annotated)[1].tofile(output / 'calibration.png')
            print(f'Sprawdz ramki: {output / "calibration.png"}')
            if input('ENTER: ramki poprawne, rozpocznij test; R: ponow kalibracje. ').strip().lower() != 'r':
                break
        guards = [ConfirmMaximum(v['maximum']) for v in values]
        (output / 'calibration.json').write_text(json.dumps({'rectangles': pair,
                    'frame_shape': frame.shape, 'readings': readings}, indent=2), encoding='utf-8')
        del engine
        gc.collect()
        tuning = []
        config = Path(__file__).resolve().with_name('obs_auto_settings.json')
        key = cache_key(frame, pair, args)
        key['pipeline'] = 'sequential_analyzers_v1'
        selected = cached_threads(config, key) if args.threads == 'auto' and not args.retune else None
        if args.threads != 'auto':
            selected = int(args.threads)
        elif selected is None:
            selected, tuning = tune(camera, pair, baseline)
            try:
                temporary = config.with_suffix('.tmp')
                temporary.write_text(json.dumps({'key': key, 'threads': selected, 'tuning': tuning}, indent=2), encoding='utf-8')
                temporary.replace(config)
            except OSError as error:
                print(f'Nie mozna zapisac ustawienia Auto: {error}')
        else:
            print(f'AUTO: zapisane ustawienie {selected} watkow; --retune powtarza pomiar.')
        engine = make_engine(selected)
        _, _, frame = camera.get()
        read_pair(engine, frame, pair)
        hp_analyzer = HpMpAnalyzer(engine, pair)
        print(f'Wybrano {selected} watkow; cel {args.target_fps:g} odczytow/s.')
        seq, _, _ = camera.get()
        initial_seq = seq
        start = time.perf_counter()
        log_time = 0
        next_due = start
        health_check = start
        cpu_start = time.process_time()
        print('Test: graj, zmieniaj HP/MP; zachowaj uklad UI. Ctrl+C konczy i zapisuje wyniki.')
        try:
            while time.perf_counter()-start < args.seconds:
                delay = min(next_due, start+args.seconds)-time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                if time.perf_counter()-start >= args.seconds:
                    break
                # Get newest frame AFTER pacing, never sleep holding an old frame.
                item = camera.get_marked(seq)
                if item is None:
                    publish(latest_path, 'BRAK_KLATEK')
                    events.append({'elapsed_s': time.perf_counter()-start, 'status': 'BRAK_KLATEK'})
                    print('BRAK_KLATEK: dane niewazne', flush=True)
                    continue
                seq, received, frame, stamp, marker_status, marker_age = item
                analysis_start = time.perf_counter()
                next_due = analysis_start + 1/args.target_fps
                if marker_status != 'OK' or marker_age is None or marker_age < 0:
                    for guard in guards:
                        guard.update(None)
                    publish(latest_path, marker_status if marker_status != 'OK' else 'ZEGAR_NIEZGODNY')
                    events.append({'elapsed_s': analysis_start-start, 'status': marker_status})
                    if analysis_start-log_time >= 1:
                        print(f'{marker_status}: dane niewazne', flush=True)
                        log_time = analysis_start
                    continue
                analysis = hp_analyzer.analyze(frame)
                readings = analysis['readings']
                end = time.perf_counter()
                statuses = [g.update(r['value']) for g, r in zip(guards, readings)]
                result_age = marker_age + (end-received)*1000
                status = result_status(marker_status, marker_age, (end-received)*1000, statuses)
                if result_age > args.max_age_ms:
                    status = 'WYNIK_ZBYT_STARY'
                # If transmission failed DURING OCR, don't publish a valid result.
                with camera.condition:
                    newest = camera.marked
                    if camera.error:
                        status = 'BLAD_KAMERY'
                    elif newest is None or end-newest[1] > .5:
                        status = 'BRAK_KLATEK'
                publish(latest_path, status, readings, result_age, args.max_age_ms, statuses)
                row = {'sequence': seq, 'elapsed_s': end-start,
                       'status': status, 'valid': status == 'OK',
                       'marker_age_ms': marker_age, 'result_age_ms': result_age,
                       'marker_ms': camera.marker_ms,
                       'prepare_ms': analysis['prepare_ms'],
                       'recognition_ms': analysis['recognition_ms'],
                       'crop_sizes': json.dumps(analysis['crop_sizes']),
                       'ocr_ms': (end-analysis_start)*1000,
                       'wait_ms': (analysis_start-received)*1000,
                       'received_to_result_ms': (end-received)*1000}
                for name, reading, bar_status in zip(['hp', 'mp'], readings, statuses):
                    row[name] = json.dumps(reading, ensure_ascii=True)
                    row[name+'_status'] = bar_status
                rows.append(row)
                if end-health_check >= 15:
                    recent = [r for r in rows if r['elapsed_s'] >= end-start-15]
                    slow = sum(r['ocr_ms'] > 1500/args.target_fps for r in recent)
                    if recent and slow/len(recent) > .5:
                        print('AUTO: utrzymujace sie spowolnienie. Powtorz test z --retune przy obecnym obciazeniu.', flush=True)
                    health_check = end
                if end-log_time >= 1:
                    print(f'{status} | SUROWY HP={readings[0]["value"]} | '
                          f'SUROWY MP={readings[1]["value"]} | '
                          f'OCR={row["ocr_ms"]:.1f} ms | wiek wyniku={result_age:.1f} ms', flush=True)
                    log_time = end
                if args.preview:
                    strip = np.vstack([cv2.resize(crop_bar(frame, rect), (800, 40)) for rect in pair])
                    cv2.imshow('HP / MP - Q konczy', strip)
                    if cv2.waitKey(1) & 255 == ord('q'):
                        break
        except KeyboardInterrupt:
            pass
        finally:
            duration = time.perf_counter()-start
            with camera.condition:
                captured = camera.count-initial_seq
            report = {'threads': selected, 'mode': args.threads, 'target_pairs_per_second': args.target_fps,
                      'process_cpu_machine_percent': 100*(time.process_time()-cpu_start)/duration/(os.cpu_count() or 1),
                      'marker_ms': stats([r['marker_ms'] for r in rows]),
                      'prepare_ms': stats([r['prepare_ms'] for r in rows]),
                      'recognition_ms': stats([r['recognition_ms'] for r in rows]),
                      'valid_pairs': sum(r['valid'] for r in rows),
                      'result_age_ms': stats([r['result_age_ms'] for r in rows]),
                      'max_age_ms': args.max_age_ms, 'invalid_events': len(events),
                      'tuning': tuning, 'preview': args.preview,
                      'duration_s': duration, 'baseline_fps': baseline,
                      'camera_fps': captured/duration, 'pairs_per_second': len(rows)/duration,
                      'pairs': len(rows), 'ocr_ms': stats([r['ocr_ms'] for r in rows]),
                      'wait_ms': stats([r['wait_ms'] for r in rows]),
                      'received_to_result_ms': stats([r['received_to_result_ms'] for r in rows])}
            if rows:
                with (output / 'readings.csv').open('w', newline='', encoding='utf-8') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            (output / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            (output / 'events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
            print('\n--- PODSUMOWANIE ---\n' + json.dumps(report, indent=2))
            print(f'Wyniki: {output}')
    finally:
        camera.stop.set()
        camera.thread.join(timeout=3)
        cv2.destroyAllWindows()
        publish(latest_path, 'ZATRZYMANY_PROGRAM')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Przerwano.')
    except Exception as error:
        print(f'BLAD: {error}', file=sys.stderr)
        sys.exit(1)
