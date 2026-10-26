FROM node:22-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OCR_ENGINE=rapidocr \
    MODEL_LOCAL_ONLY=1 \
    RAPIDOCR_MODEL_DIR=/opt/models/rapidocr \
    OCR_CPU_THREADS=2 \
    PORT=10000 \
    TRAINING_DATA_DIR=/app/storage/training_data
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY download_model.py ./
# Model files are baked into the image; a server restart needs no download.
RUN python download_model.py
COPY --from=frontend-build /frontend/dist ./frontend/dist
EXPOSE 10000
# One worker preserves the existing in-memory scan cache. Threads allow health
# checks and recalculations while a scan is running.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 900 'backend.app:create_app()'"]
