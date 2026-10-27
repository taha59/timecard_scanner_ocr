# Device OCR optimization — October 26, 2026

The recognition model and vocabulary are unchanged: PP-OCRv6 medium,
`PP-OCRv6_rec_medium.onnx`, SHA-256
`eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b`.
No quantization, retraining, reduced input resolution, or altered time arithmetic
was introduced.

## Four-thread follow-up (same recognition model)

The current default is up to four WASM CPU threads inside one OCR worker/model
session. The count is capped by reported CPU cores; browsers without isolation
or shared memory use one. A startup failure still retries once with one thread.
`VITE_OCR_THREADS=1`, `2`, or `4` provides an explicit build-time limit.

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
