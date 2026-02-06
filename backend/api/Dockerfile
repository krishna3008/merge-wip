# Dockerfile for API Gateway
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Expose port
EXPOSE 8000

# Run API Gateway
CMD ["python", "-m", "uvicorn", "backend.api.api_gateway:app", "--host", "0.0.0.0", "--port", "8000"]
