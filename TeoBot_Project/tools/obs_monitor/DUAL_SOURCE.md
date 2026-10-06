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

Sidebar acceptance also checks the number of separated ink groups against the
number of OCR digits. A mismatch returns current=null with
reason=digit_count_mismatch; it cannot supply a sidebar-only value. This is a
conservative omission check, not proof that individual digits are correct.
Broken or touching glyphs can affect grouping. Rejected count mismatches are
included in opt-in conflict captures even when top text remains usable.
No additional OCR calls are made by this check.

Regression replay: 18 manually inspected reference crops, 17 correctly accepted
and the known 111 -> 1 error rejected. Windows replay is required because OCR
outputs differ between installed Tesseract builds.

Accuracy-first diagnostics:

```bash
python tools/obs_monitor/test_obs_tesseract.py --strict-verification --capture-dataset --capture-conflicts --seconds 180
```

Strict verification forces sidebar OCR on every analyzed frame and only exposes
an exact value after two consecutive frames agree across both sources on the
same current AND top maximum, separated by at most 250 ms. Any missing source,
conflict, value change or longer gap resets confirmation. This is not a guarantee
of correctness: both OCR paths use Tesseract and can share errors. Calibrated
color-fill consistency is now required by this flag. Covered top bars cannot produce a
confirmed strict value even if sidebar digits are readable.

Dataset capture samples analyzed frames at up to 5/s, capped at 2000. It stores
raw lossless top strips, sidebar counters, sidebar colored bars, nearby sidebar
context and same-frame analysis metadata. Sampling follows actual processing
cadence, not guaranteed fixed-rate video; the extra disk work affects latency.
Each ZIP contains blank labels.csv for independent manual truth labels. No
saved OCR values are copied into labels. Keep UI layout fixed after calibration.

Offline replay without OBS:

```bash
python tools/obs_monitor/replay_hp_mp_dataset.py ocr_dataset_TIMESTAMP.zip > replay.jsonl
python tools/obs_monitor/replay_hp_mp_dataset.py ocr_dataset_TIMESTAMP.zip --labels labels.csv > labeled_replay.jsonl
```

Replay reports source agreements and errors against filled manual labels.
Blank labels are excluded from accuracy counts; agreements without truth labels
are not accuracy. It does not simulate live expiry, temporal confirmation or
actions. All screenshots and labels remain outside the repository.

Strict color check measures contiguous fill intervals on both top and sidebar
bars before temporal confirmation. It permits top HP color changes, excludes
the permanently colored sidebar bevel, and uses two pixels of top rounding
margin / three sidebar pixels. A readable candidate must fit every available
interval; at least one interval must be available. Noncontiguous fill, disagreeing
rows, missing calibration or changed image shape can make color evidence unknown.
Color is never converted to an exact current value or used to correct OCR.
Some occlusions can resemble empty or colored pixels, so this is a consistency
check, not a universal occlusion detector or correctness guarantee. Both source
OCR agreements and temporal confirmation remain required in strict mode.
latest.json now includes fill evidence, fill_status and confirmation.

Capture includes actual full-bar calibration crops for future color replays.
For earlier datasets without calibration crops, --color-check uses the first
sample; independently check that its bars are full before interpreting results.

```bash
python tools/obs_monitor/replay_hp_mp_dataset.py ocr_dataset_TIMESTAMP.zip --color-check > replay_color.jsonl
```

Validation on 791 recorded samples: among 1,430 recorded resource-level current
agreements, color agreed with 1,423 and rejected 7. Six had visually corrupted
HP maxima; one had a visibly occluded sidebar MP bar. This is a consistency
result, not measured accuracy on all samples. Full Tesseract replay also ran on
all 1,582 resource crops without errors. Regression suite: 28 tests, including
repeated wrong maximum rejection and the colored sidebar bevel.

## Experimental source arbitration and glyph recovery

`--resilient-verification` implies sidebar verification on every analyzed frame.
It is mutually exclusive with `--strict-verification`; existing modes retain
previous behavior. This mode is for evaluation, not a claim of zero OCR errors.

- Colored foreign content in the neutral-gray sidebar counter is rejected
  before glyph recovery. This catches item icons; gray overlays may still evade
  this heuristic. The threshold is not a universal occlusion detector.
- Rejected sidebar numbers are retried as separate visible glyphs. Each glyph
  must yield the same single digit in page modes 10 and 7. Original raw text,
  rejection details and recovery text remain in diagnostics.
- Invalid top ratios are retried using a geometrically detected slash, followed
  by separate current/maximum number recognition. Long terminal UI underlines
  can be removed for segmentation. No slash is inferred from cached maxima or
  from the other counter. MP suffix recognition is unnecessary for normal OCR;
  uncertain glyph recovery can still reject an otherwise readable crop.
- Every available color interval must support a candidate; unavailable bars
  are excluded. A top candidate uses its observed maximum. A side candidate
  uses the last confirmed maximum only for checking color consistency.
- A single supported candidate can be selected when the other is missing or
  inconsistent with color. If two different currents both fit the intervals,
  neither is selected. Color never supplies an exact current value.
- Two consecutive matching candidates within 250 ms are required. A source or
  cached-maximum change resets confirmation. Source switching cannot count as
  a second confirmation of the previous source.
- Sidebar-only output remains `current_only`, with `maximum=null` and
  `percent=null`; the estimated percentage is explicitly based on cached max.
  Freshness/expiry and changed-maximum checks remain active.

Partial overlays may resemble legitimate bar fill or a different digit. The
color model and two OCR segmentation modes are not independent ground truth.
Do not interpret increased availability or repeated agreement as accuracy.

Offline evaluation, without OBS or the game:

```bash
python -X utf8 tools/obs_monitor/replay_hp_mp_dataset.py DATASET.zip --resilient-verification > replay_resilient.jsonl
python -X utf8 tools/obs_monitor/replay_side_conflicts.py CONFLICTS.zip --glyph-retry
```

Optional `--labels labels.csv` evaluates independently annotated values. Replay
uses recorded sample timestamps and the live confirmation/maximum guards, but
5 Hz dataset sampling omits intermediate live frames. Camera age, publication
expiry and actions are not simulated. A full visible calibration frame is
required; archives without calibration PNGs use their first sample, which must
be independently verified as full HP/MP. Stored OCR is not a label.

Only after offline inspection, optional live integration:

```bash
python -X utf8 tools/obs_monitor/test_obs_tesseract.py --resilient-verification --seconds 120 --capture-conflicts
```

This tool only publishes readings; it does not send healing actions.


## Fill and changing-current checks

Fill intervals include half a pixel for rounding the displayed endpoint, in
addition to the existing calibrated margin. Sidebar green/yellow item pixels
invalidate fill evidence rather than representing a lower resource percentage.
Gray or matching-color overlays may still evade the heuristic.

In resilient mode only, if both counters agree, the observed maximum equals the
last confirmed maximum, both bars are unavailable, and at least one bar has an
explicit foreign-color overlay, two fresh matching text pairs can confirm the
reading (`current_agrees_without_color`). A present conflicting color interval,
missing/rejected counter, disagreement or new maximum blocks this fallback.

Two fresh complete top/sidebar agreements supported by color may confirm a
changed current without waiting for it to stabilize (`two_frames_consistent_change`).
Both frames must have the same maximum/source/quality; the 250 ms gap limit is
unchanged. Single-source and color-unavailable observations still require an
identical current in two frames. Existing strict mode retains identical-pair
confirmation. Reset reasons are recorded so missing samples can be separated
from changing current or source/maximum changes.

To evaluate new selection/fill/confirmation against previously saved Windows
OCR observations without rerunning Tesseract:

```bash
python -X utf8 tools/obs_monitor/replay_hp_mp_dataset.py DATASET.zip --resilient-verification --saved-ocr replay_resilient.jsonl > replay_updated.jsonl
```

The archive and saved replay must refer to the same recording. Case/resource
coverage is checked, but legacy JSONL files contain no image fingerprint to
prove recording identity. Saved observations remain untrusted OCR, not labels.
This mode reruns color and decision logic on the original images; glyph OCR is
reused. Do not use the same path for the input and redirected output.

## Unavailable-color single-counter corroboration

Resilient mode removes only tiny isolated sidebar specks (at most 3x3 pixels,
area <=8 after scaling), and only in the presence of substantial glyphs. This
prevents a subpixel UI artifact from adding a fake digit group.

When both fill intervals are unavailable, one has explicit foreign-color
occlusion, the sidebar counter is rejected, and the top maximum matches the
last confirmed maximum, top text can undergo additional geometric slash and
separate-glyph recognition. Only an exactly matching recovered ratio can become
`top_glyphs_supported_without_color`. Two fresh identical candidates are still
required. A present conflicting bar, new maximum, failed corroboration or a
readable disagreeing sidebar does not enter this path. Existing strict mode
is unchanged. This is additional checking of the SAME image and Tesseract
model, not independent ground truth; shared errors remain possible.

`--saved-ocr` normally reuses OCR, but this new path lazily starts Tesseract for
previously uncorroborated top crops. Set `--directory` as usual when needed.
Manual CSV evaluation now accepts current-only labels with blank maximum fields.
Such labels evaluate current accuracy and do not validate maximum/percentage.
Manual labels and user screenshots must stay outside the public repository.

## Slow readings versus invalid observations

The pipeline defaults to `--slow-age-ms 250 --max-age-ms 5000`. Age is measured
from the OBS timestamp, including transmission/capture/processing, not just OCR.
Crossing 250 ms sets `slow_reading` in latest.json and increments summary
`slow_readings`; it does not invalidate a correct reading. The original
observation time is preserved and expiry remains observation + 5000 ms.

A short absence of new camera frames does not refresh or invalidate the last
published observation; consumers must honor its expiry. After five seconds,
missing/frozen frames or old results are rejected and temporal confirmation is
reset. Camera errors, invalid timestamps/markers and explicit program stop are
still invalid immediately. Recovery needs new confirmed observations before
publication. Standalone marker tools retain their previous default threshold.

Resilient confirmation allows up to five seconds between candidate observations.
It still requires the same current for single-source readings, or two complete
color-supported agreements for changing current. Strict mode retains its former
250 ms identical-pair gate. These checks are separate from the processing-speed
warning and from source/digit correctness.

Resource output adds `effective_maximum`, `effective_percent` and
`maximum_is_cached`. When maximum cannot be read, these fields use the last
confirmed maximum for the bot/UI percentage. The directly observed `value.maximum`
can remain null and is not relabeled as a measurement. A newly readable maximum
still goes through its existing change-confirmation check.

Next independent live/capture test:

```bash
python -X utf8 tools/obs_monitor/test_obs_tesseract.py --resilient-verification --seconds 180 --capture-dataset --capture-conflicts
```

Start with full visible HP/MP for calibration. During capture, exercise varying
HP/MP and cover the top/sidebar separately. Also capture a genuine maximum
change if possible. Inspect warnings, throughput, age and original images;
zero conflicts or valid output alone does not measure independent accuracy.
