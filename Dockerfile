# Multi-stage build: Node for frontend, Python for backend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy backend
COPY backend/ backend/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist frontend/dist

# Create data directory
RUN mkdir -p /data

ENV MONOLITH_DATABASE_PATH=/data/monolith.db
ENV MONOLITH_HOST=0.0.0.0
ENV MONOLITH_PORT=8000

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
