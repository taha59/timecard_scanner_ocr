# Render runs only the stateless API. Vercel builds frontend/ separately.
FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENABLE_SERVER_OCR=false \
    RAPIDOCR_MODEL_DIR=/opt/models/rapidocr \
    PORT=10000
COPY requirements-backend.txt ./
RUN pip install --no-cache-dir -r requirements-backend.txt
COPY backend ./backend
COPY scripts/download_device_model.py ./scripts/download_device_model.py
# Only public OCR weights are saved. Uploaded timecards are never written to disk.
RUN python scripts/download_device_model.py
EXPOSE 10000
# State is carried by the browser: requests can reach different workers/restarts.
# One worker + two threads limits baseline RAM on small instances.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 2 --timeout 120 --worker-tmp-dir /dev/shm 'backend.app:create_app()'"]
