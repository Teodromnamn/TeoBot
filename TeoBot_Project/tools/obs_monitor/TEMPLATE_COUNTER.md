# Experimental native font counters

## Hybrid fallback experiment

```bash
git pull --ff-only
/c/_MS/GIT/TeoBot_OCR_venv/Scripts/python.exe -X utf8 tools/obs_monitor/run_template_regression.py --root . --output template_regression_hybrid --ocr-fallback
```

Offline; requires the existing Tesseract installation, no game/OBS/keys. Strict
template matching runs first. A rejected template candidate gets a resident
Tesseract retry using the existing validated top/side OCR routines. Occlusion
filtering remains in force. A template-accepted candidate is not overridden by
OCR. There is no source arbitration, temporal confirmation or maximum update.

Linux reference run: 26092/26092 labeled test currents have at least one correct
candidate, with zero missing or wrong-only candidate sets. This does NOT prove
the final selected value: 184 source conflicts remain, versus 96 for templates
alone. Fallback can also return an incorrect secondary candidate. Numeric
fallback counts measure availability, not independent correctness. See
template_hybrid_results_v1.json. Existing live monitor remains unchanged.

Native/unlabeled archives no longer inherit unrelated labels*.csv files from
their parent directory. Automatic adjacent CSV discovery is restricted to the
synthetic dataset.zip/synthetic_occlusion.zip convention. Native labels must
come from the explicit hash-bound references or mapped manual-audit archive.

## Complete available-archive regression

```bash
git pull --ff-only
/c/_MS/GIT/TeoBot_OCR_venv/Scripts/python.exe -X utf8 tools/obs_monitor/run_template_regression.py --root . --output template_regression
```

No game, OBS or Tesseract required. The script discovers crop archives, handles
long-diagnostic bundles and nested synthetic hp_mp packages, and deduplicates
datasets by SHA-256. Available manual/synthetic labels are checked for matching
case coverage; native CSV crop hashes are checked when supplied. The model's
training portion is reported separately. Unlabeled archives receive no accuracy
verdict. Results go to summary.json and candidates.jsonl in the output folder.
The current prototype DOES NOT pass this larger regression: missing candidates
and wrong-only candidate sets remain. Exit code 1 indicates those test failures,
not a failure to write the report. Existing live OCR is unaffected.

The checked result is template_regression_results_v1.json: 31 unique datasets,
17388 frames, 26092 labeled test currents; 25916 have a correct candidate,
170 have no candidate and 6 retain only a source differing from the reference
in the synthetic source-skew suite. Native recordings contribute 35 of the
missing candidates and no wrong-only set. These counts do not test production
selection, confirmation or maximum recognition.

Offline experiment only. Live OCR, confirmation and actions remain unchanged.
This version reads current HP/MP, not maxima. It uses no Tesseract for recognition.
Top and side fonts have separate templates. Matching checks shape overlap, aspect
ratio and the distance to the runner-up digit; distances are not probabilities.

The frozen model uses the most frequent glyph raster per digit/source from frames
0–1999 of the manually labeled 5281-frame recording. Frames 2000–5280 and the
separate 15-case conflict recording are test frames. Frames are disjoint, but
repeated glyphs and counters may occur in both sets. New fonts/scaling are untested.

Completely covering a leading digit leaves a valid shorter number. Templates
cannot discover that missing digit from the remaining shape. Preserve the
production occlusion/layout and fill checks. Candidate availability is not
correct automatic source selection. No production integration in this version.

## Quick Windows test: no OBS or game

From TeoBot_Project after git pull:

```bash
/c/_MS/GIT/TeoBot_OCR_venv/Scripts/python.exe -X utf8 tools/obs_monitor/check_template_native.py ocr_conflicts_20261010_224456_535478.zip
```

Expected: 30 correct current candidates available, no accepted wrong candidate
in this particular archive. No Tesseract dependency for this test.

## Larger comparison

Extract the inner ocr_dataset_20261010_200323_181063.zip from the corresponding
long_diagnostic archive into a directory containing case_00000, case_00001, etc.

```bash
/c/_MS/GIT/TeoBot_OCR_venv/Scripts/python.exe -X utf8 tools/obs_monitor/benchmark_template_counter.py ocr_dataset_20261010_200323_181063 --model tools/obs_monitor/counter_templates_v1.json --compare-ocr
```

The OCR baseline uses fresh calls with resident Tesseract and its pixel cache.
Both methods use the same preliminary occlusion filter. This tests raw candidates,
not full production arbitration. Timings exclude file reads, occlusion inspection,
OBS, publication and actions. Repeated crops favor the OCR cache. Raw source
errors remain in the report even when the other source supplies a correct value.
