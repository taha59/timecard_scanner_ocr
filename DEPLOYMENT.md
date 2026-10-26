# Linux / Render deployment

The default reader is **PaddleOCR PP-OCRv6 through RapidOCR / ONNX Runtime CPU**.
It uses the small text detector and medium recognizer on every operating system.
No platform-specific OCR APIs, hosted OCR credentials, PyTorch, or GPU are required.
`OCR_ENGINE=rapidocr` selects it explicitly; `auto` selects the same reader.

## Build and run

The Dockerfile builds React, installs the CPU OCR runtime, caches the two model
files during the build, and runs Flask with Gunicorn on `0.0.0.0:$PORT`.
No timecard images are sent to an OCR provider. The image build downloads public
packages and model weights; runtime recognition defaults to offline mode.

```sh
docker build -t timecard-scanner .
docker run --rm -p 10000:10000 -v timecard-data:/app/storage timecard-scanner
```

For Render, create a Web Service from the repository and select Docker. Use
`/api/health` as its health-check path and let the Dockerfile supply the start
command. The health response identifies the loaded reader after the first scan.
Model files occupy about 90 MB; that is disk usage, not a RAM requirement.
Measure memory and scan latency on the intended host before choosing capacity.

If corrected crop labels must survive restarts, attach a disk at `/app/storage`.
The scan cache is still in memory and clears on restart. Keep one Gunicorn worker
and one service instance until that cache is moved to a shared store.

## Native Python setup

```sh
pip install -r requirements.txt
python download_model.py
# Build frontend as described in README.md, then:
gunicorn --bind 0.0.0.0:10000 --workers 1 --threads 4 --timeout 900 'backend.app:create_app()'
```

`RAPIDOCR_MODEL_DIR` controls the model cache location. The Dockerfile sets it to
`/opt/models/rapidocr`; the local default is `model_cache/rapidocr` inside the
project. `MODEL_LOCAL_ONLY=1` prevents runtime model downloads. Missing model files
produce an explicit error; there is no silent fallback to another OCR engine.

The optional legacy TrOCR reader needs `requirements-trocr.txt`,
`OCR_ENGINE=trocr`, and its own model download.

## Verification and remaining application work

See `GRID_ALIGNMENT_FIX.md` for current measured recognition results and remaining sample
errors. OCR values and notes still require review. The current app has no login
or per-user ownership of scan/training downloads. A public multi-user service
also needs authentication, ownership checks, durable storage and queued scan
jobs with quotas.

The Linux Docker build has not been executed in this session because Docker
access was declined. Tests here use the portable ONNX CPU provider. They verify the OCR implementation,
not a completed Linux or Raspberry Pi deployment.

References: [Render Docker deployment](https://render.com/docs/docker),
[Flask deployment](https://render.com/docs/deploy-flask),
[persistent disk behavior](https://render.com/docs/disks),
[RapidOCR supported model routes](https://rapidai.github.io/RapidOCRDocs/main/en/model_list/).
