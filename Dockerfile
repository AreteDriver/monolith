# Multi-stage build: Node for frontend, Python for backend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# Install Litestream + curl
ADD https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz /tmp/litestream.tar.gz
RUN tar -C /usr/local/bin -xzf /tmp/litestream.tar.gz && rm /tmp/litestream.tar.gz

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy backend, scripts, and seed
COPY backend/ backend/
COPY scripts/ scripts/
COPY demo_seed.py ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist frontend/dist

# Litestream config
COPY litestream.yml ./litestream.yml

# Create data directory
RUN mkdir -p /data

ENV MONOLITH_DATABASE_PATH=/data/monolith.db
ENV MONOLITH_HOST=0.0.0.0
ENV MONOLITH_PORT=8000

EXPOSE 8000

CMD ["litestream", "replicate", "-config", "/app/litestream.yml", "-exec", "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"]
