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
