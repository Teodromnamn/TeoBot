"""Optional Tk diagnostics. OCR/camera stay in the monitor worker thread."""
import threading
import time


class MonitorControl:
    def __init__(self):
        self.stop = threading.Event()
        self.requested = threading.Event()
        self.paused = threading.Event()
        self.message = 'Uruchamianie; pierwsza kalibracja w konsoli.'

    def request_calibration(self):
        self.paused.set()
        self.message = 'Pokaz pelne HP i MP oraz odslon oba zrodla. Kalibracja...'
        self.requested.set()

    def take_request(self):
        if not self.requested.is_set():
            return False
        self.requested.clear()
        return True

    def finish_calibration(self, error=None):
        if error:
            self.message = 'Kalibracja nieudana: ' + str(error) + '. Popraw obraz i kliknij ponownie.'
        else:
            self.message = 'Kalibracja zakonczona. Oczekiwanie na nowe potwierdzenie.'
            self.paused.clear()


def recalibrate(frame, engine, detector, reader, analyzer_factory, guard_factory):
    """Build everything locally; failed calibration never installs partial state."""
    pair = detector(frame)
    if pair is None:
        raise RuntimeError('Nie znaleziono gornych paskow')
    readings = reader(engine, frame, pair)
    values = [r.get('value') for r in readings]
    if len(values) != 2 or any(v is None or v['current'] != v['maximum'] for v in values):
        raise RuntimeError('Wymagane czytelne i pelne HP oraz MP')
    guards = [guard_factory(v['maximum']) for v in values]
    analyzer = analyzer_factory(engine, pair)
    side = analyzer.calibrate(frame, readings, guards) if hasattr(analyzer, 'calibrate') else None
    return pair, guards, analyzer, readings, side


def resource_text(resource, now_ms):
    value = resource.get('value') if resource.get('valid') else None
    if not value:
        return 'Brak potwierdzonego odczytu', resource.get('reason', 'Oczekiwanie'), 0
    maximum = resource.get('effective_maximum')
    percent = resource.get('effective_percent')
    source = {'top_text':'gorne cyfry', 'side_text':'boczne cyfry',
              'top_and_side_text':'gorne i boczne cyfry'}.get(resource.get('source'), resource.get('source'))
    age = max(0, now_ms-resource.get('observed_at_unix_ms', now_ms))
    title = f"{value['current']} / {maximum if maximum is not None else '?'}"
    if percent is not None:
        title += f'   {percent:.1f}%'
    details = f'Zrodlo: {source} | wiek: {age:.0f} ms'
    if resource.get('maximum_is_cached'):
        details += ' | maksimum zapamietane'
    if (resource.get('text_occlusion') or {}).get('occluded'):
        details += ' | gorne cyfry zasloniete'
    sidebar = (resource.get('fill') or {}).get('sidebar') or {}
    if not sidebar.get('available') and sidebar.get('reason') in {
            'sidebar_contour_occluded', 'neutral_overlay', 'foreign_color_overlay'}:
        details += ' | boczny pasek zasloniety'
    if age > 250:
        details += ' | wolny odczyt'
    return title, details, percent or 0


def run_dashboard(monitor, pipeline):
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title('TeoBot — diagnostyka HP / MP')
    root.geometry('650x330')
    control = MonitorControl()
    pipeline.monitor_control = control
    status = tk.StringVar(value='Uruchamianie')
    ttk.Label(root, textvariable=status, wraplength=620).pack(padx=16, pady=12)
    fields = {}
    for name in ('hp', 'mp'):
        box = ttk.LabelFrame(root, text=name.upper())
        box.pack(fill='x', padx=16, pady=5)
        title, detail = tk.StringVar(), tk.StringVar()
        ttk.Label(box, textvariable=title, font=('Segoe UI', 16)).pack(anchor='w', padx=10)
        ttk.Label(box, textvariable=detail, wraplength=600).pack(anchor='w', padx=10)
        bar = ttk.Progressbar(box, maximum=100)
        bar.pack(fill='x', padx=10, pady=6)
        fields[name] = (title, detail, bar)
    buttons = ttk.Frame(root)
    buttons.pack(pady=10)
    ttk.Button(buttons, text='Ponowna kalibracja (pelne HP / MP)', command=control.request_calibration).pack(side='left')
    ttk.Button(buttons, text='Zatrzymaj', command=control.stop.set).pack(side='left', padx=10)
    state = {'finished': False, 'error': None}
    samples = []
    last_publication = None

    def worker():
        try:
            monitor()
        except BaseException as error:
            state['error'] = str(error)
        finally:
            state['finished'] = True

    thread = threading.Thread(target=worker, name='ocr-monitor', daemon=True)
    thread.start()

    def refresh():
        nonlocal last_publication
        data = pipeline.current_result()
        now = time.perf_counter()
        publication = data.get('published_at_unix_ms')
        if publication is not None and publication != last_publication:
            if any(r.get('observed_at_unix_ms') for r in data.get('resources', {}).values()):
                samples.append(now)
            last_publication = publication
        samples[:] = [stamp for stamp in samples if now-stamp < 5]

        status.set(('Blad: '+state['error']) if state['error'] else
                   'Monitor zatrzymany' if state['finished'] else
                   control.message if control.paused.is_set() or not data else data.get('status', 'Uruchamianie'))
        if data and not control.paused.is_set() and not state['finished']:
            status.set(status.get() + f' | aktualizacje z odczytem: {len(samples)/5:.1f}/s (ostatnie 5 s)')
        for name, (title, detail, bar) in fields.items():
            resource = {} if control.paused.is_set() or state['finished'] else data.get('resources', {}).get(name, {})
            text, explanation, percent = resource_text(resource, time.time_ns()//1000000)
            title.set(text); detail.set(explanation); bar['value'] = min(100, max(0, percent))
        root.after(100, refresh)

    def close():
        control.stop.set()
        if thread.is_alive():
            status.set('Zatrzymywanie; jesli konsola czeka na ENTER, nacisnij ENTER.')
            root.after(100, close)
        else:
            pipeline.monitor_control = None
            root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    refresh()
    root.mainloop()
