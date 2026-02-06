# Dockerfile for Worker POD
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Run Worker POD (project ID passed as argument)
ENTRYPOINT ["python", "backend/services/worker/worker_pod.py"]
