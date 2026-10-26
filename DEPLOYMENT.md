# Deploy Vercel frontend + Render API

This deployment uses **device OCR only**. Render serves the downloadable model,
crops photos, and calculates totals. Recognition runs in a browser worker on the
user's phone/computer. Recent Safari/Chrome, HTTPS, WebAssembly, workers,
OffscreenCanvas, and browser storage are required. Physical iPhone/Android tests
are still needed; limited-memory phones may fail inference. Manual entry remains
available; there is no automatic server OCR fallback.

## Environment settings: no .env upload

Enter values in each host's dashboard. `.env.example` and
`frontend/.env.example` are templates, not files to upload or commit with secrets.
Vite exposes every `VITE_*` value publicly in JavaScript; only public addresses
and feature flags belong there. Changing Vercel values requires a new build.
Render uses its settings at runtime and restarts/redeploys when they change.

| Host | Setting | Value |
|---|---|---|
| Vercel | `VITE_API_BASE_URL` | `https://YOUR-API.onrender.com` (no `/api` suffix) |
| Vercel | `VITE_REQUIRE_ACCESS_PASSWORD` | `true` |
| Vercel | `VITE_ENABLE_SERVER_OCR` | `false` |
| Render | `APP_ENV` | `production` |
| Render | `ALLOWED_ORIGINS` | `https://YOUR-APP.vercel.app` |
| Render | `APP_ACCESS_TOKEN` | Random private password, at least 24 characters |
| Render | `ENABLE_SERVER_OCR` | `false` |

Generate the private password with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`,
or use Render Blueprint's generated value. Share it privately with your dad.
Users type it into the frontend's unlock screen; it is held only in page memory,
sent in an Authorization header over HTTPS, and must be re-entered after refresh.
Never put it in Vercel, a `VITE_*` setting, Git, or a URL. This shared password is
for a small family deployment, not separate user accounts or per-user auditing.

## 1. Create the frontend project on Vercel

Import the repository, set **Root Directory = frontend**, framework **Vite**,
install command **npm ci**, build command **npm run build**, and output **dist**.
Use Node 24 (or a supported Node version >=22.22.2). `frontend/vercel.json`
contains the static-host settings. Do not rewrite `/api` through a Vercel Function:
the browser calls Render directly, including large image/crop/model transfers.

Reserve/obtain your stable Vercel production URL. Set the three Vercel variables
above once you know the Render URL, then deploy/redeploy. No personal photos,
model weights, Python packages, or `.env` files go in the Vercel deployment.

## 2. Create the Render backend

Import the same repository as a **Web Service**, runtime **Docker**, root directory
**repository root**, Dockerfile **./Dockerfile**. Leave start command unset; the
Dockerfile starts Gunicorn on `0.0.0.0:$PORT`. Set health-check path
**/api/health**. Alternatively, use the supplied `render.yaml` Blueprint; it
selects Free, generates the access password, and asks for `ALLOWED_ORIGINS`.

Add the four Render variables in the table, then deploy. The app refuses to start
in production if the password is missing/short or the origin allowlist is empty.
Docker downloads and verifies only the recognition weights during the build; it
does not install RapidOCR/ONNX Runtime or load a server OCR model.

The backend needs no database, persistent disk, or session affinity. Free instances
are suitable for initial testing, but can sleep and have limited RAM/CPU. Large
photos still cost memory for cropping. Requests are limited to 20 MiB / 24 MP;
images above 6 MP are resized before cropping. Each process handles one image
operation at a time; another concurrent operation receives a retryable 429.
Measure real phone uploads before committing to a hosting size.

## 3. Connect and test

Set `VITE_API_BASE_URL` to Render's HTTPS origin, then redeploy Vercel. Set Render's
`ALLOWED_ORIGINS` to the exact Vercel production origin. For additional approved
custom/preview domains, use a comma-separated list of exact HTTPS origins.
Wildcards and all-Vercel-domain allowances are intentionally unsupported.

1. Check `https://YOUR-API.onrender.com/api/health`: `ok: true`, `stateless: true`,
   `server_ocr_enabled: false`, `ocr_loaded: false`.
2. Open Vercel on iPhone Safari / Android Chrome. Unlock with the private password.
3. Consent to the ~74 MiB model download (plus ~12 MB runtime before compression).
4. Upload, optionally rotate in 90-degree steps, and run a device scan. Verify
   originals against entries. Test cancel and a second scan.
5. Refresh, unlock again, and confirm **Model ready on this device** without a
   second model download. Test **Remove downloaded model** and download again.
6. Add to Home Screen via Safari Share or Chrome menu. The app is installable,
   but still needs the backend; it is not fully offline.

401 means the access password is missing/wrong. An origin error/CORS failure means
the frontend domain differs from `ALLOWED_ORIGINS`. Check for trailing paths,
HTTP vs HTTPS, or a new Vercel preview domain. Render cold starts may require retry.

## Photo handling and statelessness

Uploads, image decoding, cropping, and calculation happen in request memory.
The app overrides Werkzeug's normal disk-spooling behavior for file uploads.
There are **no scan caches, saved photos, training endpoints, debug crop writes,
or server-side sessions**. API responses are marked `Cache-Control: no-store`.
The browser holds the returned normalized-card images and sends them with device
readings for the final calculation. That request can hit a different worker or a
fresh instance. Closing/refreshing the page loses the current timecards.

Only public model weights and application code are saved on Render. Only the OCR
model is deliberately saved in browser Cache Storage; photos/readings are not
persisted there. The service worker does not cache photos or API responses.
Hosting providers control their own request buffering/infrastructure; review their
policies if you need guarantees beyond application behavior. Prior local training
files/backups from older versions are not deleted by this update.

## Local development and checks

For same-origin local use, leave `VITE_API_BASE_URL` empty and password requirements
off. Install Python dependencies, download the verified model, and build:

```sh
pip install -r requirements-backend.txt
python scripts/download_device_model.py
cd frontend
npm ci
npm run build
cd ..
python -m backend.app
```

`python -m pytest -q` requires pytest and the fixture photos. Legacy server OCR
experiments still need `requirements.txt`, model setup, and the explicit backend
`ENABLE_SERVER_OCR=true` / frontend `VITE_ENABLE_SERVER_OCR=true` opt-ins; these
are not included in the production Docker image.

References: [Vercel Vite](https://vercel.com/docs/frameworks/frontend/vite),
[Render Docker](https://render.com/docs/docker),
[Render environment settings](https://render.com/docs/environment-variables).

## Verified in this revision

- Frontend production build and 146 Python tests passed.
- Frontend access/password retry and cancellation/configured-API tests passed.
- Linux Docker image built; five-card preparation/finalization passed with a
  read-only container filesystem, production password, and cross-origin headers.
- Real browser device recognition completed through the stateless API.
- Hosted Vercel/Render deployment and physical phone tests remain to be performed.
