# OBS monitor — testy

Python 3.10+, Windows, OBS Virtual Camera. Uruchamiaj z folderu TeoBot_Project:

```bash
python -m pip install -r requirements.txt
python -X utf8 tools/obs_monitor/test_obs_pipeline.py --seconds 120
```

OBS: dodaj plik obs_marker.html jako zrodlo Przegladarka, 544 x 32, 60 FPS. Umiesc caly znacznik na scenie gry, bez przycinania. Wlacz kamere wirtualna. Kalibracja wymaga pelnych gornych paskow HP i MP. Po kalibracji mozna grac, zachowujac rozmiar i polozenie UI.

Auto porownuje 1/2/4 watki i zapisuje wybor. --retune wymusza nowy pomiar. --target-fps 10 ustawia cel odczytow. --max-age-ms 250 ogranicza wiek wyniku od znacznika OBS do konca OCR.

Wyniki w obs_fast_results: summary.json, readings.csv, events.json, latest.json. Konsument latest.json musi sprawdzic valid ORAZ expires_at_unix_ms. Status OK nie dowodzi poprawnosci OCR; znacznik potwierdza swiezosc wyjscia OBS, nie samej gry.

Kamera odbiera pelne klatki; znacznik i HP/MP analizowane sa kolejno z jednej klatki. vision_analyzers.py zawiera HpMpAnalyzer i opcjonalny TemplateAnalyzer (wzorzec w tej samej skali UI). Nie ma jeszcze gotowego wykrywania Battle List ani automatycznej rekalibracji po zmianie UI.

Aktualizacje: Fetch pokazuje nowe commity, Pull pobiera zmiany do plikow. Korzystaj z galezi feature/automatic-hp-mp-ocr.
