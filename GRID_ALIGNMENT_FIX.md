# Measured grid correction — October 26, 2026

The reported crop bug was reproduced on `novel-five-cards.jpg`: the old detector
found only three of five cards, and the legacy estimated grid started some cells
below the top of the IN handwriting. A surviving IN word could then be interpreted
in the OUT position. The earlier fallback only ran when no cards were detected,
so it could not repair a partially detected photograph.

## Implementation

All candidate-detection passes now run for every image. Every accepted card must
have a validated sequence of fourteen printed filled OUT boxes. Eight measured
day boundaries replace the estimated strip-height offsets. The source vertical
coordinates vary by row to accommodate perspective. A robust edge fit excludes
attached rules and printed totals; duplicates are merged by their actual strip
position, without requiring all cards to have the same apparent height.

The review crops include six pixels of surrounding context. OCR field assignment
accounts for that padding, keeping the crop visible to the reviewer and the
coordinates used by the reader consistent. The detector no longer fabricates an
estimated seven-row grid when it cannot validate the printed pattern.

Recognized clock text overrides ink-density guesses. A low-ink OFF hypothesis
alone no longer creates a zero-hour day; unreadable nonblank ink remains unknown.

## Verification

The browser was used to upload the exact new file, scan five cards, and open
Employee 01's first day crop. Both `8:58 AM` and `5:07 PM` are intact, assigned to IN and
OUT respectively, producing 8:09. `measured-grid-crop-verification.png` records
that inspection.

All four supplied photographs have the correct card counts: 5, 7, 1, and 5.
Their resized (0.6× and 1.5×), rotated (2°), and perspective-warped variants also
pass the card-count and measured-grid checks: sixteen transformed-image cases.
An independently annotated source-image test verifies that Employee 01's first IN
word is inside the crop and its center is separate from OUT. An invalid solid
green rectangle is rejected instead of being treated as a day grid.

**125 automated tests pass.** These verify geometry and application behavior;
they do not establish general handwriting recognition accuracy.

## Actual OCR results and remaining work

`grid-rewrite-evaluation.json` records real recognition of all four photographs;
`grid-rewrite-summary.json` records scored errors. Recognition uses PaddleOCR /
ONNX CPU, with no Apple OCR or external inference calls.

| Photograph | Cards | Correct clock punches | Runtime here |
| --- | --- | --- | --- |
| Latest five-card photo | 5 / 5 | 44 / 48 | 48.95 s |
| Original five-card photo | 5 / 5 | 39 / 44 | 37.15 s |
| Employee 11 close-up | 1 / 1 | 6 / 6 visible worked punches | 9.08 s |
| October seven-card photo | 7 / 7 | Not fully labeled/scored | 62.47 s |

Clock scoring compares digits modulo 12 hours, as in the earlier evaluator; it
is not an AM/PM accuracy claim. The latest photo still has three missing punches,
a misread `10:30` as `10:20`, and AM/PM mistakes requiring review. Employee names
and OFF words in the left notes column are also imperfect.

The original photo's OCR score dropped from the earlier 42/44 snapshot to 39/44
after rectification changed. This regression is recorded rather than hidden by
selecting a special rendering for that file. An additional experiment using
unpadded row views and voting did not improve the two scored photos and was not
added to production. Correct alignment does not by itself solve handwriting OCR.

This fixes the reproduced crop/partial-detection defect and broadens geometric
regression coverage. These are development photos, not a held-out accuracy study;
no universal accuracy claim is justified yet. Severe distortion, occlusion, and
unreadable printing can still prevent grid validation.

To repeat the four-photo run from the project root:

```sh
python -m scripts.verify_grid_alignment
```

Ground-truth labels are used only by evaluation/tests, never by the scanner.
