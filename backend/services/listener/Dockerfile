# Dockerfile for Listener Service
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Expose port
EXPOSE 8000

# Run Listener Service
CMD ["python", "-m", "uvicorn", "backend.services.listener.listener_service:app", "--host", "0.0.0.0", "--port", "8000"]
