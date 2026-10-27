# Timecard scanner

Flask + React/TypeScript review app for handwritten TOPS 1256 cards. All time arithmetic is in the pure `backend/calculator.py`. Written employee totals are compared only after calculations. The fixture is used by tests/evaluation only; the scanner never looks up answers from it.

The current deployment defaults to device OCR and a stateless API. See [DEPLOYMENT.md](DEPLOYMENT.md) for the up-to-date Vercel + Render setup and photo handling.

The following reader evaluation notes describe the optional legacy server OCR pipeline. This is a review tool for handwritten timecards. The default OCR reader is **PaddleOCR PP-OCRv6 through RapidOCR and ONNX Runtime CPU**, with the same code path on Mac and Linux. No hosted OCR requests, Apple APIs, PyTorch or GPU are required. Public model weights are downloaded once; normal scans run offline.

See [current grid alignment results](GRID_ALIGNMENT_FIX.md) for measured accuracy and remaining errors (the [earlier OCR comparison](OCR_COMPARISON.md) records historical results), and [Linux / Render deployment](DEPLOYMENT.md) for deployment setup. Every day and notes area still needs human inspection.

## Local setup (Python 3.11+ and Node >=22.22.2)

From the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-backend.txt
python3 scripts/download_device_model.py
cd frontend
npm ci
npm run build
cd ..
python3 -m backend.app
```

Open http://127.0.0.1:5000. Flask serves the built UI and API together. This is a local address on the machine running the command, not a remotely accessible hosted preview.

For development, run Flask as above and, in a second terminal, run `npm run dev` from `frontend`. Open the Vite URL (usually http://127.0.0.1:5173). Vite proxies `/api` to Flask port 5000.

The default detector and recognizer occupy about 90 MB on disk. CPU inference needs additional RAM; benchmark on the intended server. If weights are unavailable, use **Extract crops for manual entry**. It produces real crops with empty punch fields, never fake OCR results.

For a private server, build the frontend and use a WSGI host (for example `gunicorn --workers 1 --timeout 900 --bind 127.0.0.1:5000 'backend.app:create_app()'`). Production uses a shared access password and an exact frontend-origin allowlist. It has no separate user accounts or durable scan storage. See DEPLOYMENT.md.

## Review workflow

1. Upload a photo with all green IN/OUT strips visible. OCR is local; manual mode skips it explicitly.
2. Check the visible day crops beside the IN and OUT fields. Tap a crop to enlarge it; expand View timecard for the whole card.
3. Correct the two time fields directly. No status toggle, notes confirmation, or reviewed checkbox is required. Clear both fields to exclude a day.
4. Only complete valid pairs contribute to the displayed total. An incomplete or invalid pair is excluded and flagged; the remaining valid days still total. Notes and adjustments are not included.
5. Edits trigger Python recalculation after 350 ms; stale responses are ignored. No duration math runs in React.
6. The written total is a cross-check only and cannot change calculated hours.
7. Photos and corrections stay in the current browser page. The backend has no scan cache or photo-saving/training endpoints.

OCR warnings are available under Check entry. Empty days show a dash; missing or invalid entries show an exclusion warning. The phone layout keeps visible source thumbnails, both time fields, and hours on screen without horizontal scrolling. The app does not certify a payment or execute payroll.

## Calculation rules

- Both punches include AM/PM: subtract modulo 24 hours, allowing overnight shifts.
- Either punch lacks AM/PM: subtract modulo 12 hours, with an inference flag. This cannot disambiguate shifts lasting 12+ hours. Supply explicit AM/PM when necessary.
- App totals depend on time fields, not OCR status. Two empty fields contribute nothing. Incomplete or invalid pairs remain unresolved individually and are excluded from the sum of valid pairs. Clear both fields for OFF or crossed-out days.
- Explicit shifts over 12 hours, zero-length shifts, missing punches, invalid times, low confidence and conflicting readings are flagged.
- Normalization accepts O→0, I/l→1, semicolon→colon, periods as separators, harmless trailing punctuation, and optional a.m./p.m. A single minute digit is interpreted literally (`8:0pm` → 8:00 pm).
- App calculations ignore notes and adjustments. The pure calculator retains its legacy status/adjustment mode for existing library callers; app endpoints explicitly use punch-only mode.

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

`ui_test.cjs` starts its own Flask process and exercises actual React controls and HTTP requests in jsdom: upload → 35 rows → corrected Michael punches → 51:53 → written-total independence → crop dialog, with no photo-saving controls. It does not establish visual correctness, real browser file behavior, or mobile layout. `browser_test.cjs` covers a similar flow plus mobile overflow in Chromium when available.

`evaluate.py` runs the real reader on the supplied photo and prints expected vs actual per scored cell. It reports status accuracy, clock-punch accuracy modulo 12 hours, regular totals matching, grand totals matching, and detected/expected card count. David's second row is excluded. Unknown punches are failures, not zeros. Adjustments remain unconfirmed during evaluation; grand totals are consequently unresolved until human review. The regular-total match metric is the useful automatic punch-total measurement. A model failure exits with code 2 and `evaluation: NOT RUN`, never a fabricated score.

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
| `DEBUG_CROPS_DIR` | ignored | Debug photo writes have been removed |
| `EXTRACT_PROGRESS` | unset | Print each card/day as recognition begins |
| `TRAINING_DATA_DIR` | ignored | Server photo storage has been removed |
| `PORT` | `5000` | Flask development-server port; Vite proxy assumes 5000 |

Uploads are limited to 20 MiB / 24 megapixels; images above 6 MP are resized. Photos are processed in request memory only. There is no scan cache or photo persistence.

## API

`POST /api/scan` — multipart field `image`; `device=true` prepares stateless browser recognition, or `manual=true` skips OCR. Optional `rotation` accepts 0/90/180/270. Server OCR is disabled unless explicitly enabled. Returns `{scan_id,cards,manual,message}`. Each card includes seven day objects, original card/cell/note images as PNG data URLs, raw OCR text/confidence, flags, computed integer minutes/H:MM/decimal, totals and cross-check candidates. Missing local model returns 503 with `ocr_unavailable:true`; invalid images/layout return 400.

`POST /api/calculate` — JSON `{"cards":[...]}`. Exactly seven days per card. Day fields: `status` (`worked|off|blank|crossed_out|unknown`), `in`, `out`, `adjustment_hours`, `adjustment_confirmed`, `reviewed`, and optional OCR metadata. Returns `{cards:[...]}`. Totals with any unresolved input are `null`; known punch subtotal is separate. Written total is a card-level string and never an arithmetic input.

Training/photo storage endpoints have been removed. Device preparation returns normalized cards to the browser; `POST /api/device-result` accepts those cards and device readings, without a server scan cache.

`GET /api/health` returns `{ok,ocr_loaded,ocr_engine}`. `GET /` serves the production React build.
