# Dockerfile for Watcher Service
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Run Watcher Service
CMD ["python", "backend/services/watcher/watcher_service.py"]
