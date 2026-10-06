# Same-frame sidebar verification

Run from TeoBot_Project:

```bash
python -X utf8 tools/obs_monitor/test_obs_tesseract.py --verify-side --seconds 120
```

Calibration requires full visible top and sidebar HP/MP. Sidebar text must match
top current values in the same calibration image; otherwise startup stops.
Inspect `side_calibration.png` in the result directory. Keep the UI layout fixed.
The anchor check rejects some layout changes/occlusions; it is not automatic
recalibration or a guarantee against every overlay.

Top OCR runs at the existing target rate. Sidebar counters are read at 2 Hz on
the same frame, increasing to up to 10 Hz for two seconds after disagreement or
missing data. Missing top text triggers an immediate sidebar read. Conflicts
force a recheck on the next analyzed frame. The existing analysis target limits
the actual rate. One Tesseract instance is used sequentially.

Each reading carries `verification`:
- `current_agrees`: both current values agree on this frame (maximum unverified).
- `not_checked`: this frame was not checked; no old confirmation is reused.
- `conflict`: numeric disagreement; no current value is published for that resource.
- `side_unreadable`: top text only.
- `top_unreadable`: sidebar current only, with no exact maximum/percent.
- `both_unreadable`: neither source provided a number.

`latest.json` exposes independent resource validity and expiry. A sidebar-only
value has `maximum=null`, `percent=null`, `last_confirmed_maximum` and
`estimated_percent` (null if current exceeds the cached maximum). Consumers must
check resource validity/expiry and quality, and must not treat this estimate as
a new measurement of maximum. `verified_current` never verifies the maximum.
Two repeated top readings still confirm a changed maximum; this heuristic can
accept correlated OCR errors and is not an accuracy guarantee.

Summary includes `side_checks`, `side_ms`, and `source_conflicts`.
`recognition_ms` still measures top OCR; `side_ms` includes sidebar preparation
and recognition. `ocr_ms`/result age include the entire analysis.

Without `--verify-side`, the top-only mode remains available.
Tests: `python tools/obs_monitor/check_dual_source.py` and
`python tools/obs_monitor/check_reading_contract.py`.

## Capture conflicts for diagnosis

Add `--capture-conflicts` alongside `--verify-side`. At exit, the program creates
`ocr_conflicts_TIMESTAMP.zip` in the working directory. Each case contains both
HP/MP top and side crops from the same frame, top prepared/binary images, side
binary images and raw readings with rectangles in `reading.json`. Preprocessing
is replayed deterministically without additional recognition. No full frames
are saved. The timestamp is save time, not game-render time. Raw OCR is evidence,
not a ground-truth label.

Limits: 60 cases, at most two per identical disagreement, at least five seconds
between duplicates and 0.5 seconds globally. Capture is opt-in and synchronous;
its cost is included in end-to-end analysis time and expiry checks. A storage
failure disables capture and leaves OCR running. No diagnostic mode changes the
recognition or conflict resolution rules.

Sidebar OCR now uses a tight crop around all pixels above 140 after 4x cubic
scaling, threshold 120, a 16-pixel white border, and Tesseract single-word mode
(PSM 8). The top-bar path remains PSM 7; the engine restores it after each call.
No digits are inferred from the other source. Captures record the processor ID.

Replay conflict originals on the installed Tesseract without OBS:

```bash
python tools/obs_monitor/replay_side_conflicts.py ocr_conflicts_TIMESTAMP.zip
```

This prints old/new sidebar text and saved top text for comparison, not an
accuracy score: saved OCR is not ground truth. Local validation covered 10
conflict crops and 4 older sidebar crops, all read correctly. This small sample
and a different Tesseract build do not establish live Windows accuracy.
