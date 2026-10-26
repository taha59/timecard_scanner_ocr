# Missing-punch recovery — real-photo validation

The recognition model and its weights are unchanged. The 0.90 score controls only
whether an ordinary cleaned retry can be skipped; it was never a minimum score
for populating a field. A valid time at a much lower score is still populated,
with a review flag.

## Changes

- Add a tighter photographic retry around the OUT line, excluding more of the
  handwritten Total/duration below it. Existing ordinary crops remain first.
- Run this retry only when both ordinary crop readings lack a valid clock,
  regardless of their confidence scores. A high score with missing/invalid text
  never suppresses recovery. Shared crop dependencies remain conservative.
- If ordinary/focused reads still lack a strictly parsed time, accept limited
  formatting recovery (e.g. an explicit H:MM prefix followed by stray characters,
  an OCR semicolon, or a three/four-digit clock with a lost separator).
- Never synthesize an entire missing number or fill a field from written totals,
  expected labels, names, or another employee. Bare compact numbers need a separate
  clock anchor in the same row, to avoid interpreting an isolated total as a time.
  Two times in one crop, dates, signed durations and unreadable fragments stay empty.
- Recovered values carry **Tentative OCR recovery: verify digits against source
  crop**. Confidence remains capped and every OCR row still starts unreviewed.
- The day inspector shows the raw reader text so a reviewer can see the basis of
  a suggested entry. Valid ordinary readings are not replaced just for a higher score.

## Browser check: latest supplied five-card photograph

Compared against the existing independent annotations on the same real image:

| Field | Before correct / missing / incorrect | After correct / missing / incorrect |
| --- | --- | --- |
| IN (24 expected) | 23 / 0 / 1 | 23 / 0 / 1 |
| OUT (24 expected) | 12 / 12 / 0 | 24 / 0 / 0 |

No punches were added on the annotated OFF days. Runtime increased from 27.62s
in the earlier two-thread run to 30.18s with recovery enabled. This small-sample
comparison measures clock digits modulo 12 hours, not full AM/PM correctness or
general OCR accuracy. The existing IN mistake was not repaired by this change.

A separate real close-up browser run returned all six visible worked punches and
no punches on the other days. The original five-card browser run returned 41 of
44 scored clock fields correctly, with one still missing and two incorrect. No
punches were added on its annotated OFF days. These are not held-out writer
evaluations.

## Additional native-runtime comparison on three real photographs

Same PP-OCRv6 weights and preprocessing for before/after, using the native ONNX CPU
runtime. Its pixel resizing/runtime differs from browser canvas, so these scores
are reported separately and must not be pooled with browser scores.

| Photo | Before correct / missing / incorrect | After correct / missing / incorrect |
| --- | --- | --- |
| Latest five-card photo, 48 clock fields | 38 / 9 / 1 | 47 / 0 / 1 |
| Original five-card photo, 44 scored fields | 37 / 3 / 4 | 39 / 1 / 4 |
| Real close-up, 6 worked fields | 6 / 0 / 0 | 6 / 0 / 0 |

The annotated crossed-out row is excluded, as in the existing evaluation. No
additional punches appeared on OFF/blank days. There are still incorrect and
missing readings; a filled field is not automatically considered correct.

All accuracy checks in this revision used the supplied real photographs. Unit
mocks test parsing/control flow only; synthetic timecards are not used as OCR
accuracy evidence. Private images and per-employee reading logs are not published.
The application still processes photos in memory and keeps no server scan cache.
