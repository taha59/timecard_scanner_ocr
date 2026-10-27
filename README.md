# Timecard Scanner

A web application for turning photos of handwritten **TOPS 1256 seven-day timecards** into editable clock-in/clock-out entries and calculated employee hours. One photo can contain several cards.

The current interface shows a source crop, Time in, Time out, and Hours for each day. Users correct the times directly. The first employee is expanded; the others are collapsible. Only complete, valid time pairs contribute to the total. There are no status selectors, notes/adjustment controls, or reviewed checkboxes in the current UI.

**Browser OCR does not mean the photo stays entirely on the device.** Flask receives the photo to find and crop the cards. The browser reads the handwriting, then Flask interprets those readings and calculates hours. An internet connection to the backend is still needed.

This document describes the current source code. [Flow diagrams](docs/FLOW_DIAGRAMS.md) show the architecture, requests, and core feature flows. Older evaluation reports in the repository describe earlier implementations and are not the specification for the current UI.

## Tech stack

| Part | Actual implementation |
| --- | --- |
| Frontend | React 19, TypeScript, Vite 6, plain CSS. Most UI and state live in `frontend/src/main.tsx`; there is no client router or separate state-management library. |
| Browser recognition | `onnxruntime-web` (`^1.24.3` in `package.json`), WebAssembly CPU inference in one Web Worker, and `OffscreenCanvas` for crop preprocessing. No browser GPU provider is selected. |
| Recognition model | PaddleOCR **PP-OCRv6 Medium**, `PP-OCRv6_rec_medium.onnx`. The pinned manifest contains its size, SHA-256 checksum, and character vocabulary. |
| Backend | Flask 3, OpenCV, NumPy, Pillow. Python performs card detection, image rectification, crop creation, OCR-text parsing, and all time arithmetic. |
| Production serving | Vercel serves the static frontend. Render runs the Python API through Docker and Gunicorn. The files also support a local Flask server serving the built frontend. |
| Storage | No database, ORM, scan history, or saved-photo service. React holds the current scan in memory; browser Cache Storage holds downloaded model weights. The backend stores public model weights on disk, not uploaded timecards. |
| External downloads | The model installer downloads pinned public weights from ModelScope's RapidAI/RapidOCR repository. Optional legacy server readers can download their own weights. There is no Google, Azure, Apple, or other hosted OCR API integration in the application. |
| Optional server OCR | RapidOCR 3.10.0 with ONNX Runtime 1.31.0; an alternative TrOCR adapter uses Transformers/PyTorch. These are disabled by default and are not installed in the production Docker image. |
| Checks | pytest, plus standalone Node scripts using assertions, esbuild, JSDOM, and Testing Library. |

## Project structure

```text
backend/
  app.py                  Flask factory, routes, access checks, uploads, static files
  extractor.py            Green-strip detection, normalized cards, day/punch crops
  device_ocr.py           Collect browser tasks and replay returned OCR readings
  device-model.json       Pinned recognition model metadata and vocabulary
  ocr_common.py           Strict clock parsing and tentative formatting recovery
  calculator.py           Pure time parsing, arithmetic, flags, totals, cross-checks
  recognizer.py           Reading type, manual reader, reader factory, optional TrOCR
  rapid_recognizer.py     Optional server RapidOCR pipeline; shared choose_reading()
frontend/
  src/main.tsx            App component, scan/edit requests, rotation, inspector, UI
  src/api.ts              API origin, in-memory bearer token, fetch wrapper
  src/device-ocr.ts       Model download/cache and worker lifecycle/cancellation
  src/ocr.worker.ts       ONNX session, crop inference, text decoding, timing
  src/ocr-policy.ts       Crop ordering and conditional retry/skip rules
  src/ocr-threads.ts      CPU thread selection
  src/scan-progress.tsx   Progress message to percentage/progress-bar display
  src/style.css          Desktop and phone layouts
  public/sw.js            Install support; does not cache scans or API responses
  public/manifest.webmanifest
  vite.config.ts          React build, development API proxy and isolation headers
  vercel.json             Vercel build and response-header configuration
  .env.example            Public frontend configuration template
scripts/
  download_device_model.py  Download/check the browser recognition model
  update_device_manifest.py Rebuild metadata/vocabulary after a model change
  test_*.cjs               Current focused browser-logic checks
  test_deployment.py       Smoke test for a separately running local container
  verify_*.py              Developer photo/grid verification utilities
tests/                    Python calculation, layout, API, OCR-policy, privacy tests
fixtures/                 Local real-photo fixtures and expected labels
model_cache/              Downloaded weights; ignored by Git
Dockerfile                Minimal production API image; downloads recognition weights
render.yaml               Render service configuration
requirements-backend.txt  Default API dependencies, without server OCR inference
requirements.txt          Development/test and optional RapidOCR dependencies
requirements-trocr.txt    Additional optional TrOCR dependencies
.env.example              Backend runtime configuration template
pytest.ini                Limits pytest discovery to tests/
download_model.py         Downloads/warms the selected optional server OCR reader
evaluate.py               Legacy server-reader comparison against local annotations
probe_layout.py           Local crop diagnostic; writes a contact image when run
docs/FLOW_DIAGRAMS.md      Mermaid diagrams and their source-code references
```

`frontend/dist/` is generated by the frontend build. Local `backups/`, evaluation logs, screenshots, and historical fix reports are not application runtime components. Private fixture photos are excluded from the public checkout; tests that use them need those local files. `browser_test.cjs` and `ui_test.cjs` are older UI harnesses that still reference removed status/review controls; they are not the current check commands below.

## How a scan works

### 1. Open the app and prepare the model

`App()` checks browser support and, after any password unlock, requests `GET /api/device-model`. Device OCR requires a secure context (HTTPS or localhost), Cache Storage, Workers, WebAssembly, and OffscreenCanvas.

If the model is not cached, the user chooses **Agree & download model**. `downloadModel()` fetches the weights from the backend, checks the exact byte count and SHA-256 against the manifest, and saves the verified response in Cache Storage. The current model is 76,629,984 bytes, approximately 74 MiB when rounded up for the UI.

The cache is named `timecard-device-model-v1`; entries are keyed by model version and checksum. Storage persistence is requested but not guaranteed. Refreshing the page normally reuses the cache; browser eviction or **Remove downloaded model** can require another download. Removing the model also terminates the active worker.

### 2. Choose and rotate a photo

`accept()` accepts the first selected/dropped image, creates a preview, and clears old results. `rotateSource()` changes orientation in 90-degree steps and invalidates previous results.

The rotated preview is made with Canvas, with a maximum 1600-pixel side. **The upload is still the original file plus a rotation value**, not that smaller preview. Flask applies EXIF orientation, rejects inputs above 24 megapixels, reduces images above approximately 6 megapixels, and applies the requested clockwise rotation. The request-body limit is 20 MiB.

### 3. Find cards and create recognition tasks

`scan()` posts multipart data to `/api/scan` with `image`, `rotation`, and `device=true`.

`detect_cards()` does not OCR the entire photo. It uses green color masks and connected components to find printed IN/OUT strips. `bar_geometry()` requires fourteen regularly spaced filled OUT boxes, from which it derives the seven day boundaries. It fits the strip edge and uses `cv2.remap()` to build a normalized **310 × 785** image for each card. It rejects photos whose grid cannot be validated. The device route allows at most 20 cards.

`extract(..., layouts=layouts)` runs with a collecting `DeviceRecognizer`. Instead of invoking a model, its `read()` records PNG crop tasks. A task ID hashes the reading mode, RGB image dimensions, and pixels, so identical tasks are deduplicated and can be reconstructed later.

The response is `{layouts, tasks}`. `layouts` contains normalized card PNG data URLs; tasks contain crop PNG data URLs, IDs, and retry dependencies. Both stay with the browser while it recognizes handwriting. No server scan session is saved.

### 4. Read handwriting in the browser

`recognizeOnDevice()` loads the cached weights into `ocr.worker.ts`, or reuses an already initialized worker. There is **one worker and one model session**, not four separate model copies.

The default uses four WASM CPU threads only when the browser reports at least four threads and supports cross-origin isolation/shared memory. Otherwise it uses one. A build can explicitly request one, two, or four through `VITE_OCR_THREADS`; insufficient reported cores fall back to one. An initialization failure or 30-second initialization timeout gets one retry using a fresh single-thread worker. There is no automatic fallback to server OCR.

For each crop, the worker resizes to height 48, uses a tensor width between 320 and 1024, converts RGB pixels to normalized BGR channel planes, and runs the model. It decodes the highest-scoring characters, removing blank tokens and repeated adjacent tokens (CTC decoding). The raw character score is retained as `quality`; returned `confidence` is capped at 0.79.

The loaded model/vocabulary can remain in worker memory for five idle minutes. Per-scan crop/readings dictionaries are not retained for later scans. Page exit, cancellation, or model removal terminates the worker.

### 5. Interpret the returned text and calculate hours

The browser sends `{layouts, readings}` as JSON to `/api/device-result`. This sends normalized card images back as well as OCR text. `unpack_layouts()` validates the PNG dimensions and rebuilds the same crops. A replaying `DeviceRecognizer` looks up readings by their deterministic task IDs, then `extract()` assembles cards and days.

All app calculation routes call `calculate_cards(..., punch_only=True)`. The API returns cards, images, parsed fields, warnings, computed amounts, cross-checks, and a new `scan_id`. This UUID identifies the response in the UI; it is not a saved server record or a retrieval key.

### 6. Inspect and correct

The UI shows seven rows per employee. The source crop remains visible on phones and opens in a larger inspector. **View timecard** shows the whole normalized card. Names, time fields, and written totals can be edited.

`editDay()`/`editCard()` call `update()`, which updates React state immediately and waits 350 ms before posting the **whole cards array**, including its existing image fields, to `/api/calculate`. Flask recomputes every card. Older requests are aborted and a revision counter prevents late responses from replacing newer edits. Totals are shown as pending/unavailable while recalculation is pending or fails; React does not calculate durations itself.

## OCR parsing and recovery

The default browser path reads individual crops, not a whole-photo OCR transcript. It still recognizes names, written totals, notes, and status-related text in addition to punches. Although notes/status/review fields remain in the payload and extraction logic, the current UI hides them and app arithmetic ignores them.

Crop tasks are processed in this order:

| Stage | Crop and retry rule |
| --- | --- |
| Primary | Original photographic IN/OUT crops and required text crops. |
| Cleaned | Ink-only punch crops. A dependent cleaned retry may be skipped when all its original readings are clear valid clocks with raw quality at least 0.90. |
| Focused | Tighter photographic punch crop, especially trimming the OUT crop before handwritten totals. Skipped if an ordinary crop already has a readable time, regardless of score. |
| Label edge | Wider crop starting at normalized x=190, when ink touches the old boundary. Also checks valid-looking hours starting with 0, 1, or 2 that might have lost a leading 1. |

Shared tasks are skipped only when all their dependencies permit it. Skipped tasks have explicit empty readings and a reason; they are not fabricated OCR results.

`clock_text()` accepts a clock-shaped string, removes spaces, corrects selected `I/l/O/o/S/s` confusions, retains a complete AM/PM suffix, and validates through `parse_time()`. A nonnumeric unrecognized suffix can be dropped rather than treated as AM/PM. `choose_reading()` normally prefers original, cleaned, then focused valid readings. A valid wider reading can fill an unreadable field or restore a leading `1` with matching minutes and compatible meridiem.

If no strict candidate succeeds, `tentative_clock_text()` can repair formatting, such as `1125PM` to `11:25pm` or a visible `H:MM` prefix with short trailing noise. It rejects certain ambiguous/date-like/multiple-clock inputs. Compact-digit repairs require a readable clock in the other punch; they are cleared when both fields are only compact guesses. These are heuristics, not proof of the intended time.

For example, `I0 : 5S p.m.` becomes `10:55pm`. A clipped `0:55pm` remains invalid; the wider image must actually produce a better reading. Raw text, alternatives, recovery flags, and disagreements remain in the result. Warnings appear under **Check entry**. Confidence is not a calibrated accuracy percentage: the normal 0.79 cap is below the calculator's default 0.80 warning threshold. Valid low-score times can still populate fields; 0.90 controls retry skipping, not whether a field may be filled.

## Calculation rules

The public functions in `backend/calculator.py` are pure: they copy their inputs and perform no OCR, network calls, or storage.

| Input in a day row | Current app behavior |
| --- | --- |
| Both fields empty | Zero contribution; the UI displays a dash. Clear both fields to exclude an OFF or crossed-out day. |
| One field missing, or an invalid clock | That row's computed amount is `null`; it is excluded from the sum and flagged. Other valid days still total. |
| Both clocks valid, both explicitly AM/PM | Subtract using modulo 1440 minutes, allowing overnight work. |
| Either clock lacks AM/PM | Subtract using modulo 720 minutes and add an inference warning. This cannot distinguish a long shift from a short one with the same clock digits. |
| Notes or adjustment amounts | Ignored in app totals. No status toggle or reviewed flag is needed. |

Internally, amounts contain integer `minutes`, an `hm` string such as `8:09`, and a decimal-hours string rounded to two places using `Decimal` with half-up rounding. Equal clock times compute zero and get a warning; explicitly calculated shifts over 12 hours are also flagged. No break deductions or overtime rules are implemented.

`totals.regular` is the sum of complete valid pairs. `totals.complete` is false if any row is incomplete/invalid, even though the partial total remains available. `totals.grand` equals the punch total in app mode because adjustments are zero.

Written totals are interpreted **after** arithmetic and cannot select OCR readings or change hours. A value such as `27.07` has both an hours:minutes and decimal-hours interpretation; the response reports comparisons and warnings. The current UI displays them under the employee total.

The calculator also retains a legacy mode: direct callers that omit `punch_only=True` still get status-based exclusions, reviewed-row warnings, confirmed adjustments, and unresolved full totals. `evaluate.py` and some older diagnostic scripts use that mode; their totals do not necessarily describe the current app workflow.

## API and data flow

All API responses use `Cache-Control: no-store`. When an access token is configured, every API endpoint except health requires `Authorization: Bearer <password>`; preflight OPTIONS requests do not require that bearer token. Origin checks still apply.

| Method and route | Request | Response/purpose |
| --- | --- | --- |
| `GET /api/health` | No bearer needed | Service health, stateless flag, server OCR enabled/loaded state. |
| `GET /api/access` | Bearer when configured | Confirms the supplied shared password. |
| `GET /api/device-model` | Bearer when configured | Model version, filename, bytes, checksum, vocabulary, weights URL. |
| `GET /api/device-model/weights` | Bearer when configured | Recognition model from the configured model directory; 503 if missing. |
| `POST /api/scan` | Multipart `image`, optional `rotation`; `device=true` or `manual=true` selects those paths | Device path: layouts/tasks. Manual/server path: assembled cards and totals. |
| `POST /api/device-result` | JSON `layouts`, `readings` | Rebuilds crops, parses browser readings, returns calculated cards. |
| `POST /api/calculate` | JSON `cards` | Validates and recalculates edited cards, without OCR. |

`/api/device-result` accepts at most 1200 readings, each with text of at most 500 characters and a confidence between 0 and 1. Normalized layouts must be 1–20 PNGs of exactly 310 × 785 pixels. `/api/calculate` expects 1–20 cards with exactly seven day slots each.

A per-process nonblocking semaphore permits one `/api/scan` or `/api/device-result` image operation at a time; concurrent image work receives 429. Bad input normally returns 400, wrong/missing access returns 401, disallowed origins or disabled server OCR return 403, and unexpected processing failures return a generic 500 JSON error.

There is no database step. `MemoryUploadRequest` keeps multipart upload streams in `BytesIO` rather than temporary upload files. Layouts and results are carried by the browser between independent requests, so subsequent requests need not hit the same process. Application routes do not save photos, corrections, training samples, or scan history. Developer tools such as `probe_layout.py` and verification scripts can write local diagnostic images/reports when deliberately run.

### Access, cancellation, progress, and Home Screen support

- **Access:** `api.ts` holds the shared password in a module variable and adds it to request headers. It is not put in localStorage, cookies, or the frontend build. Refreshing requires unlocking again when the gate is enabled. This is a shared gate, not a user-account system.
- **Cancellation:** `cancelScan()` increments the revision and aborts the active request. During device recognition, the abort handler terminates the worker. Late results are ignored. Aborting an HTTP request does not implement cancellation of OpenCV work already running on the server.
- **Progress:** `ScanProgress` converts worker task counts to a percentage bar. Download progress uses received bytes. Preparation/model startup/results checking use indeterminate indicators when no percentage is available. A percentage measures task completion, not seconds remaining.
- **Timing:** the automatically opened Scan timing panel shows total time, crop preparation, model startup/reuse, reading, results checking, reported CPU threads, actual OCR threads, and read/skipped crop counts. Reading time excludes preparation; preparation includes upload, network, and backend work. These measurements are not uploaded as telemetry.
- **Home Screen:** the manifest, icons, and small service worker provide install support. `sw.js` has no response-caching implementation. Model caching is separate; this is not a fully offline application.

### Manual and optional server modes

**Manual entry** posts `manual=true` to `/api/scan`. `UnavailableRecognizer` returns empty text while the server still finds actual cards/crops. It does not require model download or generate fake OCR. Users fill the times; empty rows initially contribute zero. Card-grid detection is still required.

**Server OCR** is visible only with `VITE_ENABLE_SERVER_OCR=true` and is accepted by the API only with `ENABLE_SERVER_OCR=true`. Enabling the frontend flag also makes server mode the initial UI selection. The first server scan lazily loads the reader selected by `OCR_ENGINE`; `auto` and `rapidocr` select RapidOCR, while `trocr` selects TrOCR. Failure to load returns 503, not fabricated results.

The RapidOCR path reads full normalized cards and day rows with text detection, then original/cleaned punch crops if necessary. Its PP-OCRv6 small detector and medium recognizer differ from the recognition-only browser pipeline. TrOCR uses a handwriting model with constrained time-token generation. Neither optional reader uses Apple OCR. These paths exist in source but are not exercised by the default device-only Docker deployment; their quality on new photos is not established by browser benchmarks.

## Local setup

Use **Python 3.11+** and **Node >=22.22.2** (Node 24 is a suitable choice). The following shell commands are for macOS/Linux; on Windows, activate the environment with `.venv\Scripts\Activate.ps1` instead.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-backend.txt
python scripts/download_device_model.py
cd frontend
npm ci
npm run build
cd ..
python -m backend.app
```

Open **http://127.0.0.1:5000/**. No environment variables or database setup are required for the default local device/manual setup. The backend serves `frontend/dist/` after the build. Without that build, `/` returns a small API-description JSON response instead of the UI.

The downloader needs internet access and writes verified public weights to `model_cache/rapidocr/`. It reuses an existing verified file. The browser separately downloads those weights from Flask after consent.

For React hot reload, keep Flask running and start a second terminal:

```bash
cd frontend
npm run dev
```

Open the Vite URL, normally **http://127.0.0.1:5173/**. `vite.config.ts` proxies `/api` to port 5000. Both Vite and Flask's static responses set the isolation headers used by threaded OCR. If an explicit origin configuration causes a local 403, include the exact development origin in `ALLOWED_ORIGINS`.

`python -m backend.app` binds to `127.0.0.1`, not the whole LAN. Device OCR on a phone requires a supported secure origin; an ordinary HTTP LAN address does not satisfy the secure-context check.

### Environment variables

Backend variables are runtime settings. Flask **does not automatically load the root `.env` file**: export variables in your shell or configure them in the host dashboard. Vite reads its own frontend environment files at build/dev startup; its `VITE_*` values are public and need a rebuild for production changes.

| Backend variable | Default | What reads it / purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `create_app()` treats exactly `production` as production configuration. |
| `APP_ACCESS_TOKEN` | Empty | Shared bearer password. Production requires at least 24 characters. |
| `ALLOWED_ORIGINS` | Empty | Comma-separated exact frontend origins; production requires nonempty HTTPS origins. No wildcard matching. |
| `ENABLE_SERVER_OCR` | `false` | Enables the optional inference route; unnecessary for device/manual mode. |
| `PORT` | `5000` in the module runner | Local listening port; Docker defaults to 10000 and Gunicorn binds to it. |
| `RAPIDOCR_MODEL_DIR` | `model_cache/rapidocr` under the repo | Weights directory used by downloader, weight endpoint, and optional RapidOCR. Docker sets `/opt/models/rapidocr`. |
| `OCR_ENGINE` | `auto` | Optional server reader: `auto`, `rapidocr`, or `trocr`. |
| `MODEL_LOCAL_ONLY` | `1` | Optional server readers load cached weights; `0` allows their library downloads. |
| `OCR_CPU_THREADS` | `2` | CPU inference setting for optional server readers; not browser threads. |
| `TROCR_MODEL` | `microsoft/trocr-base-handwritten` | Optional TrOCR model name/path. |
| `BLANK_INK_THRESHOLD`, `OFF_INK_THRESHOLD` | `.015`, `.035` | Extraction ink heuristics; not app total inclusion rules. |
| `EXTRACT_PROGRESS` | Unset | Any nonempty value prints card/day extraction progress on the backend. |

| Frontend variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Empty | Same-origin `/api` by default. For split hosting, use the backend HTTPS origin with no path or `/api` suffix. HTTP is permitted only for localhost loopback addresses. |
| `VITE_REQUIRE_ACCESS_PASSWORD` | `false` | Shows the shared-password unlock screen. Set true when the API has a token. |
| `VITE_ENABLE_SERVER_OCR` | `false` | Exposes optional server OCR and selects it initially; does not enable it on the backend. |
| `VITE_OCR_THREADS` | `4` | Requested worker WASM CPU threads: `1`, `2`, or `4`. Unsupported/insufficient hardware uses one; an invalid configured value currently selects a limit of two. |

Use `.env.example` and `frontend/.env.example` as reference templates. Do not copy production placeholder origins into local development unless you replace them. Never put `APP_ACCESS_TOKEN` in a `VITE_*` variable or commit a real environment file.

### Optional legacy server OCR setup

This is separate from the minimal setup above. For RapidOCR, activate the virtual environment and run:

```bash
pip install -r requirements.txt
python download_model.py
export ENABLE_SERVER_OCR=true
export OCR_ENGINE=rapidocr
export MODEL_LOCAL_ONLY=1
python -m backend.app
```

`download_model.py` explicitly allows downloads and warms the selected reader. For TrOCR, install `requirements-trocr.txt` and select it before downloading:

```bash
pip install -r requirements-trocr.txt
export OCR_ENGINE=trocr
python download_model.py
```

To expose either reader in the UI, set `VITE_ENABLE_SERVER_OCR=true` for the frontend and rebuild it, and start Flask with `ENABLE_SERVER_OCR=true`. The minimal production Docker image does not include these optional inference packages.

## Deployment

The supplied deployment layout is **Vercel frontend + Render API**, detailed in [DEPLOYMENT.md](DEPLOYMENT.md).

- Vercel's project root is `frontend/`, build command is `npm run build`, and output is `dist`. `frontend/vercel.json` sets COOP/COEP isolation headers, content-type/referrer protection, and no-cache for the service-worker file.
- Set public frontend values `VITE_API_BASE_URL=https://YOUR-API.onrender.com`, `VITE_REQUIRE_ACCESS_PASSWORD=true`, `VITE_ENABLE_SERVER_OCR=false`, and optionally `VITE_OCR_THREADS=4`.
- Render uses the root `Dockerfile`/`render.yaml`. Set `APP_ENV=production`, a private `APP_ACCESS_TOKEN` of at least 24 characters, `ALLOWED_ORIGINS=https://YOUR-APP.vercel.app`, and `ENABLE_SERVER_OCR=false`.
- Docker installs only `requirements-backend.txt`, copies backend source/model metadata and the model installer, and downloads verified recognition weights during the build. It does not copy/build the frontend. Its `/` normally returns API information, while Vercel serves the UI.
- Gunicorn runs one worker with two request threads, a 120-second timeout, and `/dev/shm` worker temporary storage. These server request threads are separate from the browser's four OCR CPU threads.
- There is no database, persistent photo disk, or sticky-session requirement. `/api/health` is the configured health check. Production startup rejects missing/short passwords or missing origin configuration.

The repository describes a deployment, but an arbitrary clone cannot establish the current live host settings or physical-phone compatibility from source alone. Those must be checked in the hosting dashboards and target browsers.

## Checks and developer tools

With local private fixtures available, install the development dependencies and run the Python suite:

```bash
pip install -r requirements.txt
python -m pytest -q
```

The focused frontend checks use the installed frontend dependencies and a modern Node version:

```bash
node scripts/test_ocr_threads.cjs
node scripts/test_ocr_policy.cjs
node scripts/test_ocr_reuse.cjs
node scripts/test_scan_cancel.cjs
node scripts/test_access.cjs
```

These check thread selection, retry rules, worker reuse/startup/cancellation, stale request handling, and access configuration. They are not real-model accuracy benchmarks. The frontend build also runs TypeScript checking through `tsc -b`.

`tests/test_punch_only.py` covers the current app arithmetic; `tests/test_calculator.py` also covers legacy library behavior. Other Python tests cover real-fixture layouts, task replay, upload-memory behavior, API validation, and production configuration. Mocked OCR tests verify plumbing rather than handwriting accuracy.

`evaluate.py` uses the optional server reader and local annotations, compares clock digits modulo 12 hours, and defaults to legacy calculation mode. The `scripts/verify_*.py` helpers produce local reports. Do not treat those outputs as browser accuracy or AM/PM accuracy without inspecting their implementation. `scripts/test_deployment.py` expects a separately configured local container on port 5002 with its disposable test password; it is not part of default pytest discovery.

To understand the runtime visually, continue with [docs/FLOW_DIAGRAMS.md](docs/FLOW_DIAGRAMS.md).
