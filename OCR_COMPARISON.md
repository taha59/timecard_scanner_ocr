# Platform-independent OCR comparison — October 26, 2026

This is a historical snapshot. See [the measured-grid correction](GRID_ALIGNMENT_FIX.md) for current behavior, verification and recognition results.

The selected reader is **PaddleOCR PP-OCRv6**, using RapidOCR 3.10.0 and ONNX Runtime
1.31.0 on CPU. Detection uses `PP-OCRv6_det_small.onnx`; recognition uses
`PP-OCRv6_rec_medium.onnx`. Both model files together occupy about 90 MB on disk.
This is the default for both `OCR_ENGINE=auto` and `OCR_ENGINE=rapidocr`.

## Measured sample accuracy

All scores use the supplied photo, the same 44 labeled punches, and clock
comparison modulo 12 hours. Employee 08's crossed-out second row is excluded from
scoring. Unreadable punches count as errors. No fixture labels or written totals
are available to the scanner.

| Reader / pipeline | Correct punches |
| --- | --- |
| Original TrOCR pipeline, recorded baseline | 10 / 44 (22.73%) |
| TrOCR with repaired crops and clock grammar, exploratory run | 26 / 44 (59.09%) |
| PP-OCRv5 English mobile, full-card recognition | 34 / 44 (77.27%) |
| PP-OCRv5 server, full-card recognition | 31 / 44 (70.45%) |
| PP-OCRv6 medium, full-card recognition alone | 38 / 44 (86.36%) |
| **PP-OCRv6 medium with row context and crop fallbacks** | **42 / 44 (95.45%)** |

The Paddle comparisons above came from exploratory runs on this same image.
The final integrated result is reproducible using:

```sh
pip install -r requirements.txt
python download_model.py
python evaluate.py --json-output evaluation-rapidocr.json
```

The final integrated run also classified 33/34 scored day statuses correctly and matched two regular card totals. The full integrated log is `evaluation-rapidocr.log`. Model weights are fetched
once; the evaluation and normal image recognition work offline. The implementation
uses ONNX CPU inference on CPU without platform-specific OCR APIs. Linux deployment and
ARM throughput have not been benchmarked in this session.

## Why it improves the readings

Original row images preserve fine strokes lost by hard thresholding. The reader
tries row recognition first, then full-card context, and only then photographic
and cleaned punch crops if no valid time was obtained. Conflicting valid readings
retain alternatives and receive a review flag. Raw text remains in the API output.
The OFF word fallback requires an exact high-confidence reading and cannot
supersede a row containing a valid clock. No duration or written total influences
which punch is read.

## Remaining errors and limits

The two unresolved punches in this sample are Employee 06's day 2 IN (`10:35`) and
Employee 09's day 4 IN (`11:30`). Both remain empty rather than repairing ambiguous OCR
characters into a plausible time. Employee 09's large OFF on day 3 is also missed and
needs a manual status correction. Crossed-out rows require human inspection.
Notes and adjustments remain unconfirmed, so grand totals stay unresolved.

This is one development photo, not a held-out accuracy study. More writers,
cameras and card photographs are needed to establish general accuracy. The
reader remains a human-reviewed extraction tool.

Sources: [RapidOCR model support](https://rapidai.github.io/RapidOCRDocs/main/en/model_list/),
[RapidOCR model definitions](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml).
