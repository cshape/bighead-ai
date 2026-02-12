# ---- Stage 1: Build frontend ----
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --production=false

COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.10-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/ 2>/dev/null || true

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Create directories the app expects
RUN mkdir -p static/audio

# Environment defaults (override at runtime)
ENV PORT=8000
ENV SERVE_FRONTEND=true

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --ws wsproto"]
