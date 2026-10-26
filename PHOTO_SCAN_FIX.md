# New-photo scan regression — October 26, 2026

This is a historical snapshot. See [the measured-grid correction](GRID_ALIGNMENT_FIX.md) for current behavior, verification and recognition results.

Both uploaded photos failed before OCR with `No timecard strips found`.
Crisp printed green rules and labels connected to the filled IN/OUT bar, producing
wide components that the detector rejected as invalid strips.

The repair adds a fallback that distinguishes actual green printing from paper
tint, removes thin rules and text strokes, and rejects narrow day-label components
so they cannot become duplicate cards. Fourteen repeated filled OUT boxes recover
the seven row boundaries, avoiding clipped first punches and accommodating gradual
perspective changes down the card. The original detection path remains unchanged
when it succeeds.

Time recognition now ignores written totals below the punch band. OCR-only clock
normalization accepts S → 5 inside a clock field (for example `5:0SPM` → `5:05pm`),
retaining raw text and review flags. Explicit AM/PM disagreements are now flagged
as well as disagreements in clock digits.

## Actual API verification

`new-photo-verification.json` and `new-photo-verification.log` record real local
OCR requests through Flask's `/api/scan`, not a fake recognizer.

| Input | Before | After | Measured OCR scan time here |
| --- | --- | --- | --- |
| Seven-card group photo | HTTP 400, no cards | HTTP 200, 7 cards / 49 rows | 67.69 seconds |
| Employee 11 close-up | HTTP 400, no cards | HTTP 200, 1 card / 7 rows | 9.49 seconds |

The close-up's six clock punches match the visible three worked days. Day 3 AM/PM
is partly unreadable and remains inferred. The durations are 11:35, 8:05, and 5:00,
a known punch subtotal of 24:40. The handwritten `24 hours 40 minutes` across lower
rows is not a new shift or an adjustment. Lower-row status and note guesses still
need review; the app does not automatically certify the card total.

The group photo scans successfully but still contains OCR mistakes, missing
punches, and crossed-out/blank/status ambiguities. No overall accuracy percentage
is claimed for it. Employee names and notes also require correction.

Regression coverage includes both real images at 0.6×, 1× and 1.5× scale, manual
HTTP scans with the correct card counts, clock normalization, AM/PM conflicts,
and exclusion of written daily durations from OUT candidates. The original
five-card photo remains at 42/44 correct punches and 33/34 statuses after the fix.
All 104 automated tests pass.

To repeat the real OCR requests from the project root:

```sh
python -m scripts.verify_photo_scans
```

No fixture answers are used by detection or recognition.
