# Day 5: container for the HR Assistant API (built by Cloud Build when deploying to Cloud Run)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRPC_VERBOSITY=ERROR

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user (security best practice)
RUN useradd --create-home appuser
USER appuser

# Cloud Run sets $PORT (8080 by default)
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}