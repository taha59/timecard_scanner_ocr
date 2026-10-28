# Timecard Scanner

A web app that reads handwritten TOPS 1256 timecards and calculates employee hours. Users upload a photo, check the extracted times against the cropped images, and correct any mistakes.

## Run locally

Requires **Python 3.11+** and **Node.js 22.22.2+**.

```bash
# Install backend dependencies and download the OCR model
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-backend.txt
python scripts/download_device_model.py

# Install and build the frontend
cd frontend
npm ci
npm run build
cd ..

# Start the app
python -m backend.app
```

Open **http://127.0.0.1:5000**. No environment variables or database setup are needed locally.

For frontend development, keep Flask running and run `npm run dev` inside `frontend/` in another terminal. Open **http://127.0.0.1:5173**; Vite forwards API requests to Flask.

On Windows, activate the virtual environment with `.venv\Scripts\Activate.ps1` instead.

## Tech stack

| Component | Technology | Responsibility |
| --- | --- | --- |
| Frontend | React, TypeScript, Vite | Uploads, image previews, editable times, and results |
| Backend | Flask, OpenCV, Pillow, NumPy | Finds cards, creates crops, parses OCR text, and calculates hours |
| OCR | PaddleOCR PP-OCRv6 Medium through ONNX Runtime Web | Reads handwriting in a browser worker |
| Hosting | Vercel + Render | Serves the frontend and backend |

There is no database. The current scan lives in page memory; downloaded model weights are cached in the browser.

## How it works

1. **Prepare:** The user downloads the OCR model once, chooses a photo, and optionally rotates it in 90-degree steps.
2. **Crop:** The frontend sends the photo to `/api/scan`. Flask finds the printed green strips and separates each card into seven day rows and individual time crops.
3. **Recognize:** A browser worker runs OCR on those crops. It tries alternative crops when a time is unclear.
4. **Calculate:** The frontend sends the readings to `/api/device-result`. Flask cleans up the text, validates the times, and calculates hours.
5. **Correct:** The user edits times beside their source crops. After a 350 ms pause, `/api/calculate` returns updated totals.

See [Flow diagrams](docs/FLOW_DIAGRAMS.md) for the architecture and step-by-step request flows.

## Main features

- **Multiple employees:** One photo can contain several cards. Each employee has collapsible details.
- **Live results:** Finished cards appear while the others are read. You can view crops immediately; editing unlocks when processing finishes or is canceled.
- **Source images:** Day crops stay beside the time fields. Tap a crop to enlarge it or expand **View timecard** for the full card.
- **Direct editing:** Enter Time in and Time out without changing a status or marking a row reviewed.
- **Automatic totals:** Complete, valid time pairs count toward the total. Empty rows contribute nothing; incomplete or invalid rows are excluded and flagged. Notes and adjustments are not included.
- **Written-total comparison:** The handwritten total is a cross-check; it never changes calculated hours.
- **Manual entry:** **Extract crops for manual entry** provides the images without running OCR.
- **Model comparison:** Medium is the default. Select PP-OCRv6 Small to test faster recognition; both models are cached separately. Small can miss more handwriting.
- **Progress and timing:** A progress bar shows recognition progress. **Scan timing** shows processing durations and the actual thread count.
- **Cancellation:** Users can stop a scan and retry.

Include AM/PM when correcting times, especially for overnight or long shifts. If either time lacks AM/PM, the calculator uses a 12-hour interpretation and shows a warning.

## Where to find the code

| File | Start here when working on… |
| --- | --- |
| `frontend/src/main.tsx` | UI, scan requests, rotation, source inspector, or editing |
| `frontend/src/style.css` | Desktop and phone layouts |
| `frontend/src/api.ts` | API URL and request headers |
| `frontend/src/device-ocr.ts` | Model download, browser cache, worker reuse, or cancellation |
| `frontend/src/ocr.worker.ts` | Model inference and OCR text decoding |
| `frontend/src/ocr-batches.ts` | Per-card task order, shared crops, and retry dependencies |
| `frontend/src/ocr-policy.ts` | Crop retry and skip rules |
| `backend/app.py` | API routes, uploads, access checks, or response validation |
| `backend/extractor.py` | Card detection and crop boundaries |
| `backend/device_ocr.py` | Preparing crop tasks and combining returned readings |
| `backend/ocr_common.py` | Cleaning messy OCR strings into time candidates |
| `backend/calculator.py` | Time validation, day hours, totals, or warnings |
| `backend/device-model*.json` | Medium/Small model filenames, checksums, sizes, and vocabulary |
| `tests/` and `scripts/test_*.cjs` | Backend and frontend-logic checks |

The app uses **punch-only calculation mode**. The calculator also contains older status/adjustment behavior, so app calls explicitly pass `punch_only=True`.

## Deployment configuration

Use [DEPLOYMENT.md](DEPLOYMENT.md) for the full Vercel and Render setup. The configuration templates are `.env.example` and `frontend/.env.example`.

| Host | Required settings |
| --- | --- |
| Vercel | `VITE_API_BASE_URL=https://YOUR-API.onrender.com`, `VITE_ENABLE_SERVER_OCR=false` |
| Render | `APP_ENV=production`, `ALLOWED_ORIGINS=https://YOUR-APP.vercel.app`, `ENABLE_SERVER_OCR=false` |

Vite settings are public build-time values. Backend settings are runtime environment variables; Flask does not automatically load the root `.env` file. The app opens directly without signing in.

## Checks

```bash
# Backend tests
pip install -r requirements.txt
python -m pytest -q

# Frontend build and focused checks
npm run build --prefix frontend
node scripts/test_ocr_threads.cjs
node scripts/test_ocr_policy.cjs
node scripts/test_ocr_reuse.cjs
node scripts/test_scan_cancel.cjs
node scripts/test_access.cjs
```

Photo-based tests require the private local fixtures, which are excluded from the public repository.
