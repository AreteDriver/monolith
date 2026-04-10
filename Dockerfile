# Multi-stage build: Node for frontend, Python for backend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# curl (Litestream disabled — see below)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Litestream temporarily disabled (2026-04-09): retention pruning was broken,
# shadow WAL grew to 1.3GB on the 3GB volume, filled the disk, locked SQLite,
# and stalled chain ingestion for 5 days. Volume extended to 10GB; using Fly
# scheduled snapshots (5 retention) for backup until Litestream config is fixed.
# To re-enable: restore the ADD/RUN above, restore COPY litestream.yml, and
# wrap CMD back in `litestream replicate -config /app/litestream.yml -exec`.

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy backend, scripts, and seed
COPY backend/ backend/
COPY scripts/ scripts/
COPY demo_seed.py ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist frontend/dist

# Litestream config (disabled — retained for easy re-enable)
# COPY litestream.yml ./litestream.yml

# Create data directory
RUN mkdir -p /data

ENV MONOLITH_DATABASE_PATH=/data/monolith.db
ENV MONOLITH_HOST=0.0.0.0
ENV MONOLITH_PORT=8000

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
