# Device OCR optimization — October 26, 2026

The recognition model and vocabulary are unchanged: PP-OCRv6 medium,
`PP-OCRv6_rec_medium.onnx`, SHA-256
`eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b`.
No quantization, retraining, reduced input resolution, or altered time arithmetic
was introduced.

## Four-thread follow-up (same recognition model)

The current default is up to four WASM CPU threads inside one OCR worker/model
session. Four threads are used only when the browser reports at least four CPU threads;
otherwise the default uses one. Browsers without isolation or shared memory
also use one. A startup failure still retries once with one thread.
`VITE_OCR_THREADS=1`, `2`, or `4` provides an explicit build-time setting;
if fewer CPU threads are reported than requested, inference uses one.
Scan timing opens automatically after a scan and shows total time, crop
preparation, model startup/reuse, OCR reading, actual OCR threads, results
checking time, reported CPU threads, and processed/skipped crops. No timing
telemetry is uploaded.
The main scan indicator shows a handwriting progress bar and percentage;
server preparation and final checking use an indeterminate indicator. Crop
counts remain in Scan timing. The percentage tracks recognition tasks, not an
estimate of remaining seconds.

Real supplied photos, browser WASM, same computer, cached weights, current
label-edge recovery code in both configurations:

| Photo | Two threads total / reading | Four threads total / reading | Total reduction |
| --- | ---: | ---: | ---: |
| Five cards | 32.93 / 31.57 s | 20.87 / 19.33 s | 36.6% |
| Seven cards | 47.57 / 45.70 s | 29.99 / 28.13 s | 37.0% |

A reversed-order seven-card repeat measured 29.66 s with four threads and
48.01 s with two (38.2% lower total), again with identical statuses and times.

The final default-four production build repeated five cards in 20.23 s
(18.81 s reading), with identical fields to the two-thread baseline.

Both configurations inferred the same 248/309 and 360/448 crops respectively,
with identical day statuses and IN/OUT fields (35 + 49 rows, 168 time fields).
This compares outputs, not correctness against annotations. No synthetic
photos were used. The model, input dimensions, crop policy, parsing, cancellation,
privacy and cache behavior are unchanged. Real photos and raw results remain
local. These desktop measurements do not predict speed or battery use on every
phone; physical iPhone/Android testing remains necessary.

## Earlier optimization measurements (historical two-thread default)

Same supplied five-card photograph, cached model, same computer and browser:

| Configuration | Total | Reading | Crops inferred |
| --- | ---: | ---: | ---: |
| Previous implementation, one thread | 55.25 s | 53.77 s | 220 |
| Conditional fallbacks + reuse, one thread | 51.78 s | 50.53 s | 207 |
| Repeat scan, loaded model reused, one thread | 51.96 s | 50.97 s | 207 |
| Conditional fallbacks, two threads | 27.62 s | 26.37 s | 207 |

The two-thread result was approximately 50% faster end to end. All 35 day statuses
and 70 IN/OUT fields matched the previous implementation on this photo. This is
an output-regression comparison, not a claim that every reading is correct or a
prediction of speed on every phone. Physical iPhone/Android testing remains.

## Changes

- Browser isolation headers allow up to two WASM threads when supported. Browsers
  without cross-origin isolation/SharedArrayBuffer retain single-thread inference.
  `VITE_OCR_THREADS=1` can explicitly force the old threading level for diagnosis.
- Primary crops run before dependent cleaned fallbacks. A cleaned fallback is
  skipped only when *all* original crops depending on it have an unambiguous valid
  clock string and raw recognition score >=0.90. That score is a heuristic, not a
  calibrated correctness probability. Returned confidence stays capped at .79.
  Legacy tasks without dependency metadata remain fully read.
- A skipped fallback is represented explicitly, never as an invented time. The
  selected original time is unchanged. Since disagreements with an unread crop
  cannot be detected, affected rows say **Alternate OCR crop not checked: verify
  original crop**. Ambiguous/invalid originals still get both versions and retain
  disagreement checks. All rows still require human review.
- Shared fallback crops are skipped only if all dependencies qualify. A crop also
  needed as a primary reading is never skipped. No day is declared OFF/blank to
  save processing time.
- One worker/model stays loaded for up to five idle minutes. Crop images and
  reading dictionaries are local to each scan. Cancel/pagehide/removing the model
  terminate the worker; a later scan reloads it from the existing browser cache.
- Input and output tensors are explicitly disposed; one image canvas is reused.
- A Scan timing disclosure shows actual processing time, thread count, inferred
  crop count, and avoided fallbacks without sending timing telemetry anywhere.

The backend remains stateless and does not save photos. Model storage consent
and browser-cache removal behavior are unchanged.

## Runtime startup compatibility

Runtime module/binary URLs use a new cache key so browsers with pre-isolation
cached assets fetch the current COEP-enabled headers. Startup has a 30-second
watchdog and one single-thread retry on initialization failure; cancellation
still terminates the active worker. The retry uses the same cached model weights.

Live verification after rollout: five synthetic cards completed in 26.70s
(9.18s crop preparation, 0.68s model startup, 14.56s recognition on two threads).
113 of 183 synthetic crop tasks were inferred; 70 fallbacks were avoided. This
synthetic case is separate from the real-photo before/after benchmark above.

## Faster server crop preparation — October 28, 2026

The phone diagnostics identified backend work as the preparation bottleneck:
37.84 seconds server processing, including 25.49 seconds crop creation; response
download was 0.44 seconds. This release targets that backend work.

- Recognition task PNGs use compression level 1 (lossless) rather than the normal
  level 6. Their decoded RGB pixels, dimensions, task IDs and retry dependencies
  are unchanged.
- The collecting device scan does not encode review images that are discarded.
  Result reconstruction still supplies all visible source images.
- A collecting DeviceRecognizer reuses punch preparation within the request.
  Returned readings are not cached across requests and the server loads no OCR.
- Full-card PNGs and final review-image encoding retain level 6. The normalized
  layouts posted back to the API and later result/edit payloads are unchanged.

Local Flask-route medians, three repetitions per configuration, real photos:

| Cards / photo | Previous preparation | Optimized preparation | Previous crop creation | Optimized crop creation |
| --- | ---: | ---: | ---: | ---: |
| Five / latest group | 0.867 s | 0.545 s | 0.608 s | 0.279 s |
| Five / original group | 0.763 s | 0.463 s | 0.543 s | 0.238 s |
| One / close-up | 0.206 s | 0.149 s | 0.111 s | 0.051 s |
| Seven / group | 1.351 s | 0.853 s | 0.926 s | 0.414 s |

Multi-card preparation was about 37–39% faster locally; crop creation about
54–56% faster. These are preparation measurements, not fresh phone or Render
speed measurements. No native/browser recognition model was run in this test.
Every task image was decoded and checked for identical RGB pixels, dimensions,
ID and dependency metadata against the previous release. Normalized layouts
were byte-for-byte identical. Empty-reading replay also returned identical
cards, verifying plumbing rather than handwriting accuracy.

The tradeoff is a larger initial response: seven cards increased from 11.30 to
16.34 MB before HTTP compression (gzip: 8.46 to 12.07 MB). Later result responses
remained 5.55 MB before compression. The phone's next scan should be measured
with the existing diagnostics to check actual server savings and download cost.
The OCR model, browser inference code, recognition thresholds, crop geometry,
and source images shown to users are unchanged. Health reports
`device_crop_png_compression: 1` to identify the updated backend.

## Reading and results diagnostics

A subsequent phone report measured 122.22 seconds total, with 21.95 seconds
preparation, 87.29 seconds reading on four threads, and 12.40 seconds results
checking (354 crops read, 91 skipped). The preparation improvement is measured;
the cause of the increased reading time is not yet established.

Scan timing now separates crop-image decoding, input preparation, model
inference, recognized-text decoding, tensor cleanup, and other worker time.
Results checking also separates request wait, download, JSON parsing, and backend
layout reconstruction, entry/source-image reconstruction, and response building.
These are elapsed durations including scheduling delays. The instrumentation does
not change model weights, input pixels, recognition rules, threads or retries.


## Skip unused note recognition and hidden previews — October 28, 2026

The latest phone scan took 88.17 seconds: preparation 23.21, startup 0.65,
reading 52.45, and results 11.71. Inference accounted for 50.82 seconds of
reading; image decoding was only 0.86 seconds. Results reconstruction took
9.81 seconds on the backend.

App scans now skip note recognition. Notes/adjustments are absent from the UI
and do not contribute to punch-only totals. The API also stops PNG-encoding
separate note and cleaned-punch previews that the UI never displays. It still
returns the exact same full-card and day images. Legacy extractor callers keep
notes and auxiliary images by default. Older browser tabs can submit extra note
readings safely; the result endpoint ignores those unused readings.

Local measurements on real photos (preparation medians of three runs; results
one replay per configuration with empty readings):

| Photo | OCR tasks before → after | Results response before → after | Results replay before → after |
| --- | ---: | ---: | ---: |
| Latest five cards | 309 → 274 | 3.85 → 2.84 MB | 0.279 → 0.227 s |
| Original five cards | 293 → 258 | 3.85 → 2.85 MB | 0.272 → 0.224 s |
| One card | 59 → 52 | 0.73 → 0.54 MB | 0.054 → 0.044 s |
| Seven cards | 448 → 399 | 5.55 → 4.11 MB | 0.450 → 0.361 s |

These tests do not run the OCR model or predict phone inference time. They check
that retained task IDs, decoded RGB pixels, dependencies, normalized layouts,
and visible result images are unchanged. Separate fixed-reading replay tests
verify that time fields and recovery metadata are unchanged; these are plumbing
checks, not handwriting accuracy measurements. No synthetic timecards are used.
The model, four-thread default, time-crop geometry and fallback rules are unchanged.
Health identifies the new backend with `scan_profile: "punch-only-v2"`.


## Optional PP-OCRv6 Small comparison — October 28, 2026

Medium remains the default. The OCR model selector offers PP-OCRv6 Small as an
explicit speed test. Both are PaddleOCR PP-OCRv6 recognizers from RapidAI's
[pinned v3.10.0 ONNX distribution](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml).
Small is 21,234,383 bytes, versus Medium's 76,629,984 bytes. Its SHA-256 is
`6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`.
The vocabulary extracted from Small's ONNX metadata is identical to Medium's.

Local Chromium/WASM tests use four threads, real photos, the actual browser
worker, identical prepared tasks, and the same Flask result parser. No native
OCR, synthetic timecards or remote photo uploads are used. Fresh browser contexts
hold each model under a separate version/checksum cache key. Each measured scan
starts a fresh worker; download and startup are excluded from Reading below.
A repeat timing pass ran without the Python test suite competing for CPU.

| Photo | Medium reading | Small reading | Reduction |
| --- | ---: | ---: | ---: |
| Five cards | 16.63 s | 4.25 s | 74.4% |
| Seven cards | 26.12 s | 6.98 s | 73.3% |

Five-card timing is one reverse-order pass (Small then Medium). Seven-card values
average two runs each, ordered Small, Medium, Medium, Small. Medium read 311/399
crops, skipping 88; Small read 325/399, skipping 74. Retry policy is unchanged;
different recognition text/quality naturally changes which fallbacks run.
These desktop times do not predict iPhone or hosted end-to-end performance.
Backend preparation and results costs remain.

Accuracy checks use the existing manual transcriptions for two real five-card
photos. A correct field must match the transcribed hour/minute on a 12-hour clock;
colon/dot separators are normalized. AM/PM correctness, names, written totals,
seven-card accuracy, and payroll-total accuracy are not scored by this metric.

| Photo | Medium correct fields | Small correct fields | Missing fields: Medium / Small |
| --- | ---: | ---: | ---: |
| Latest five-card photo | 47/48 | 44/48 | 0 / 2 |
| Original five-card photo | 41/44 | 40/44 | 1 / 2 |
| Combined | 88/92 | 84/92 | 1 / 4 |

Neither model populated extra time fields on the annotated off/blank rows in
these two photos. Small also dropped AM/PM suffixes in several comparisons.
The measured tradeoff supports offering Small for testing, not claiming equal
accuracy or replacing Medium as the default. Cropping, parsing, retry thresholds,
review images, totals logic, and the four-thread policy are unchanged.

The selector requests `/api/device-model?variant=small`; weights are served by
`/api/device-model/weights?variant=small`. Omitting the variant keeps Medium.
The backend build installs and checksum-verifies both public weight files;
inference still runs only in the browser. Each model requires its own download
consent. Switching models releases the loaded worker and loads the selected
cached bytes. Removing the selected model preserves the other cache entry.
The timing summary includes the model name so phone comparisons remain clear.


## Live employee cards — October 28, 2026

Device scans now request `live=true`, adding `card_tasks` to preparation JSON.
Each group lists the existing task IDs used by one employee. Tasks still share
one model worker and retain their existing IDs, pixels and retry metadata.
`ocr-batches.ts` schedules each card with all prerequisites for shared retries;
each unique crop is still read once. Completed-card messages carry only readings,
not another copy of the crop images.

As a card finishes, the frontend queues a one-card `/api/device-result` request
while browser OCR continues on later cards. Results appear in employee order,
with source images and calculated totals. Open previews/collapsed states survive
later arrivals. Fields are read-only until processing finishes, fails, or is
canceled. Cancellation retains completed cards and rejects late responses.
The initial backend cropping step still prepares all cards before OCR begins.
No server streaming job, saved upload or persisted results are introduced.

Actual local mobile-width Chromium tests on the real seven-card photo:

| Model | First completed card visible | Whole scan finished |
| --- | ---: | ---: |
| PP-OCRv6 Medium | 5.32 s | 27.73 s |
| PP-OCRv6 Small | 2.80 s | 9.27 s |

These are local elapsed UI timings, not iPhone/Render predictions or a claim of
higher OCR throughput. Both models returned exactly the same complete card JSON
as their own legacy global task ordering and full-batch result reconstruction.
This includes time fields, source images, recovery metadata and totals; it does
not claim either model is fully accurate against handwriting.

Preparation timing remains one request. Results breakdown sums the per-card
requests, which overlap Reading time. The summary's `Final results wait` is only
the remaining wait after OCR finishes; adding all results request durations to
Reading would count overlapping work twice. Older preparation responses without
card groups retain the previous batch behavior.
