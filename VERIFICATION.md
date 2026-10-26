# Verification on the supplied timecards.jpg

Built and tested against the actual uploaded 1600×900 photo, not an imagined or synthetic replacement.

## Passed

- 68 Python tests: pure calculator/normalization; all five supplied employee totals from ground-truth punches; written-total independence (including malformed/extreme written totals); incomplete results; separate/confirmed adjustments; real-photo layout and every cell; fake-recognizer pipeline; API validation; crop-saving/download.
- Actual-photo layout: five green-strip card anchors, seven day crops each, 35 rows. Also tested 60%/150% resizing and 2° image rotation.
- Calibration: every worked day stays above the likely-OFF ink threshold; both blank slots fall below the blank threshold. Small OFF marks can be flagged guesses; large OFF scrawls require model/human interpretation.
- TypeScript check and production Vite build passed.
- React DOM integration against an actual spawned Flask HTTP server passed. Uploaded the actual photo in manual mode; displayed 35 rows; corrected Employee 06's punches and confirmed notes; obtained 51:53 / 51.88 hours; changed written total to 0:00 without changing arithmetic; opened original punch/note images; closed dialog with Escape; saved training labels. Also simulated a failed calculation, verified stale totals disappear, and verified recovery after retry. No JavaScript runtime errors in that test.

## OCR evaluation

TrOCR `microsoft/trocr-base-handwritten` was downloaded and executed locally on CPU, with token-restricted numeric decoding. No image was sent to a hosted AI inference API.

The baseline and final measured scores are in `evaluation-baseline.json` and `evaluation.json`; detailed expected-vs-actual comparisons are in the corresponding `.log` files. The final run includes two small corrections: harmless trailing time punctuation is accepted, and low-ink OFF / exact OFF words with surrounding punctuation are shown as flagged OFF guesses. Raw OCR text is retained in output, and unreadable values remain unresolved.

Baseline: 5/44 correct punches (11.4%), 24/34 correct scored statuses (70.6%), 0/5 regular totals matching. Final: 10/44 correct punches (22.7%), 29/34 correct statuses (85.3%), 0/5 regular totals matching. No card reached a complete automatic punch total.

This accuracy is unsuitable for unattended payroll. The working route is manual review/correction. Use the review screen's saved labeled crops to build a diverse writer/photo dataset, then fine-tune a small numeric recognizer behind the adapter. Keep an unseen writer/photo validation split. The single sample is a regression fixture, not enough training or accuracy evidence.

Adjustment grand totals remain unresolved during evaluation because note confirmation is intentionally not automated. Regular-total matching is the relevant raw punch-total score. Employee 08's second day is excluded from status/punch scoring as requested. Ground-truth calculator totals passing do not demonstrate OCR accuracy.

## Not verified / limitations

- Full Chromium test could not run: the browser download was truncated; an alternate local Chromium binary exited with SIGTRAP in this runtime. The included browser test is ready for a normal browser-capable environment. jsdom integration does not verify visual rendering, mobile overflow, camera access, or real-browser upload behavior.
- No remote Flask/PyTorch host or public/private hosted preview URL is configured. The project can run locally; its localhost address is not a URL the user can open from another machine. Prior assurances that this exact backend would automatically have a hosted preview were too broad.
- No custom recognizer has been trained. No general accuracy across other photos, lighting conditions, writers, rotations, card scales or perspective is established. Crossing out remains a manual status decision.
- No payroll is paid or certified. No authentication or durable scan history is implemented. Original scan crops live in an eight-scan in-memory cache; only explicitly saved training batches persist to backend disk.
