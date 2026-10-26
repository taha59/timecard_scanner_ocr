# Timecard scanner

Flask + React/TypeScript review app for handwritten TOPS 1256 cards. All time arithmetic is in the pure `backend/calculator.py`. Written employee totals are compared only after calculations. The fixture is used by tests/evaluation only; the scanner never looks up answers from it.

This is a review tool for handwritten timecards. The default OCR reader is **PaddleOCR PP-OCRv6 through RapidOCR and ONNX Runtime CPU**, with the same code path on Mac and Linux. No hosted OCR requests, Apple APIs, PyTorch or GPU are required. Public model weights are downloaded once; normal scans run offline.

See [current grid alignment results](GRID_ALIGNMENT_FIX.md) for measured accuracy and remaining errors (the [earlier OCR comparison](OCR_COMPARISON.md) records historical results), and [Linux / Render deployment](DEPLOYMENT.md) for deployment setup. Every day and notes area still needs human inspection.

## Setup (Python 3.11+ and Node 20.19+ / 22.12+)

From the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python3 download_model.py
cd frontend
npm ci
npm run build
cd ..
python3 -m backend.app
```

Open http://127.0.0.1:5000. Flask serves the built UI and API together. This is a local address on the machine running the command, not a remotely accessible hosted preview.

For development, run Flask as above and, in a second terminal, run `npm run dev` from `frontend`. Open the Vite URL (usually http://127.0.0.1:5173). Vite proxies `/api` to Flask port 5000.

The default detector and recognizer occupy about 90 MB on disk. CPU inference needs additional RAM; benchmark on the intended server. If weights are unavailable, use **Extract crops for manual entry**. It produces real crops with empty punch fields, never fake OCR results.

For a private server, build the frontend and use a WSGI host (for example `gunicorn --workers 1 --timeout 900 --bind 127.0.0.1:5000 'backend.app:create_app()'`). This version has no user accounts, authentication, or durable scan storage. Keep it local or behind an authenticated private gateway. A Flask/PyTorch-capable host is still needed for a remote preview.

## Review workflow

1. Upload a photo with all green IN/OUT strips visible. OCR is local; manual mode skips it explicitly.
2. Open every day crop and inspect both punches and the left notes area. Correct names, status, IN, OUT, and adjustment hours. Use the full-card link to see context.
3. Set OFF, blank, or crossed out explicitly where appropriate. Crossing-out detection is not automated reliably. Ink-derived blank classifications remain flagged guesses.
4. Enter adjustments separately (`2`, `1.5`, or `1:30`). Check **Notes checked** only after checking the source, including when no note was read. Until checked, adjustments and grand totals stay unresolved. No adjustment is silently added.
5. Mark each row reviewed after correction. Edits trigger Python recalculation after 350 ms; stale responses are ignored. No duration math runs in React.
6. A missing or invalid punch leaves the card total unresolved. The known subtotal is labeled separately. Every decimal result is rounded to two places for display; internal calculations use integer minutes.
7. The written total is only a cross-check. `27.07` is evaluated as both 27:07 and 27.07 decimal hours (27:04 rounded). It cannot change punch hours. Employee 08's supplied ground truth yields 25:12 + 2:00 = 27:12, mismatching both readings.
8. **Save corrected crops** stores only reviewed rows, with valid times for worked rows, as PNGs and JSONL labels. Download the batch with the link. Saving labels does not train a model. Training data remains on the backend under `TRAINING_DATA_DIR`.

Review flags retain OCR/ink provenance, AM/PM inference and exceptional arithmetic even after a row is marked reviewed. The app does not certify a payment or execute payroll.

## Calculation rules

- Both punches include AM/PM: subtract modulo 24 hours, allowing overnight shifts.
- Either punch lacks AM/PM: subtract modulo 12 hours, with an inference flag. This cannot disambiguate shifts lasting 12+ hours. Supply explicit AM/PM when necessary.
- OFF and blank are zero; crossed out is zero with an exclusion flag. Unknown/unreadable is unresolved, never an invented zero.
- Explicit shifts over 12 hours, zero-length shifts, missing punches, invalid times, low confidence and guessed status are flagged.
- Normalization accepts O→0, I/l→1, semicolon→colon, periods as separators, harmless trailing punctuation, and optional a.m./p.m. A single minute digit is interpreted literally (`8:0pm` → 8:00 pm).
- Adjustments are parsed separately and require confirmation. Multiple or unreadable note adjustments must be entered by the reviewer.

## Vision and OCR

Green-strip proposals from multiple color/morphology passes are combined for every photo. Fourteen repeated filled OUT boxes must validate each seven-day grid. Measured day boundaries rectify row perspective; a robust strip-edge fit excludes attached rules and labels. Day crops include six pixels of context, with the same offset accounted for in OCR field assignment. Unvalidated grids are rejected instead of using estimated strip-height offsets.

Printed green ink and long rules are suppressed for diagnostic ink measurement and cleaned fallback crops. Original photographic rows remain the primary OCR input. Ink-density classifications are guesses: recognized times take priority, and a low-ink OFF suggestion cannot by itself exclude a day. All unresolved ink needs review.

`backend/rapid_recognizer.py` uses PP-OCRv6 small detection and medium recognition through the ONNX CPU provider. It reads original rows and full-card context, then tries original photographic punch crops and cleaned crops only when necessary. Raw text, alternatives and disagreements are preserved; disagreements receive a review flag. Complete valid clock prefixes are accepted without changing digits. A malformed suffix is omitted, leaving AM/PM inference flagged; malformed numeric output stays unresolved. The scanner never consults the expected labels or written totals to choose a punch.

`backend/recognizer.py` defines the replaceable `read(PIL_image, mode) -> Reading` interface. Confidence remains an uncalibrated heuristic capped below the review threshold. Exact OFF words are accepted; low-ink OFF classifications are guesses.

Optional experimental readers remain available. `OCR_ENGINE=trocr` requires `pip install -r requirements-trocr.txt` and a model download with that environment setting. Its clock grammar prevents repeated digit outputs but its sample accuracy remains lower.

Strong perspective distortion, partly hidden strips, large rotations, severe lighting changes, and crossed-out punches need more work/data. Similar strip height filtering assumes cards have roughly the same scale. Detection and OCR failures are shown rather than resolved with fixture answers.

## Tests and evaluation

```bash
python -m pytest -q
python evaluate.py --json-output evaluation.json
# First evaluation with model downloads allowed:
python evaluate.py --download --json-output evaluation.json
python probe_layout.py
cd frontend
npm run build
cd ..
node ui_test.cjs
# Optional full browser test (Flask must be running):
cd frontend
npx playwright install chromium
cd ..
node browser_test.cjs
```

`ui_test.cjs` starts its own Flask process and exercises actual React controls and HTTP requests in jsdom: upload → 35 rows → corrected Employee 06 punches → 51:53 → written-total independence → crop dialog → saved training rows. It does not establish visual correctness, real browser file behavior, or mobile layout. `browser_test.cjs` covers a similar flow plus mobile overflow in Chromium when available.

`evaluate.py` runs the real reader on the supplied photo and prints expected vs actual per scored cell. It reports status accuracy, clock-punch accuracy modulo 12 hours, regular totals matching, grand totals matching, and detected/expected card count. Employee 08's second row is excluded. Unknown punches are failures, not zeros. Adjustments remain unconfirmed during evaluation; grand totals are consequently unresolved until human review. The regular-total match metric is the useful automatic punch-total measurement. A model failure exits with code 2 and `evaluation: NOT RUN`, never a fabricated score.

`GRID_ALIGNMENT_FIX.md`, `grid-rewrite-evaluation.json`, and `grid-rewrite-summary.json` record the current pipeline's results. `OCR_COMPARISON.md` records the earlier pipeline. Earlier `VERIFICATION.md`, `evaluation.log`, `evaluation.json` describe previous readers. Ground truth totals are calculator checks, not evidence of OCR accuracy.

For poor OCR, collect corrected crops from multiple photos and writers, split by writer/photo into train and held-out validation sets, then fine-tune a small digit/sequence model behind the adapter. This single photo is useful for regression but too small to establish general accuracy. Re-run the evaluation after every extraction/model change and never use the written total to choose a predicted punch.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `OCR_ENGINE` | `auto` | RapidOCR on all platforms; accepts `rapidocr`, legacy `trocr` |
| `RAPIDOCR_MODEL_DIR` | `model_cache/rapidocr` | Directory with the two cached ONNX model files |
| `TROCR_MODEL` | `microsoft/trocr-base-handwritten` | Cached model ID or local model directory |
| `MODEL_LOCAL_ONLY` | `1` | Offline loading; `0` permits downloading public model files |
| `HF_HOME` | Hugging Face default | Model cache directory |
| `OCR_CPU_THREADS` | `2` | CPU inference threads |
| `BLANK_INK_THRESHOLD` | `.015` | Below this fraction, guess blank |
| `OFF_INK_THRESHOLD` | `.035` | Below this fraction, guess likely OFF; not proof |
| `DEBUG_CROPS_DIR` | unset | Save all day, cleaned ink, IN and OUT crops |
| `EXTRACT_PROGRESS` | unset | Print each card/day as recognition begins |
| `TRAINING_DATA_DIR` | `training_data` | Reviewed labeled crop storage |
| `PORT` | `5000` | Flask development-server port; Vite proxy assumes 5000 |

Uploads are limited to 20 MiB / 24 megapixels. Original scan crops are cached in memory for eight scans; restarting the backend clears them. Save corrections before scanning more photos or restarting. No claim of durable project hosting or permanent preview is made.

## API

`POST /api/scan` — multipart field `image`; optional `manual=true` skips OCR. Returns `{scan_id,cards,manual,message}`. Each card includes seven day objects, original card/cell/note images as PNG data URLs, raw OCR text/confidence, flags, computed integer minutes/H:MM/decimal, totals and cross-check candidates. Missing local model returns 503 with `ocr_unavailable:true`; invalid images/layout return 400.

`POST /api/calculate` — JSON `{"cards":[...]}`. Exactly seven days per card. Day fields: `status` (`worked|off|blank|crossed_out|unknown`), `in`, `out`, `adjustment_hours`, `adjustment_confirmed`, `reviewed`, and optional OCR metadata. Returns `{cards:[...]}`. Totals with any unresolved input are `null`; known punch subtotal is separate. Written total is a card-level string and never an arithmetic input.

`POST /api/training` — JSON `{scan_id,cards}`. Saves reviewed labels plus original server-cached crop bytes, never client-supplied replacement images. Returns `{saved_rows,batch}`. `GET /api/training/<batch>` downloads that batch as ZIP.

`GET /api/health` returns `{ok,ocr_loaded,ocr_engine}`. `GET /` serves the production React build.

## Public backup snapshot

This repository preserves the application before planned on-device OCR/PWA work. Employee photos, screenshots, training records, generated scan reports, installed dependencies and model weights are not included. Employee names in examples and test labels have been anonymized. Application frontend/backend code is unchanged. Photo-dependent tests require restoring your private local fixtures; the other tests run normally.
