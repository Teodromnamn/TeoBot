# Experimental native font counters

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
