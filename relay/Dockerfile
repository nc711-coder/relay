# The Relay API (the page is hosted separately on Vercel).
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY relay ./relay
COPY sql ./sql
CMD exec uvicorn relay.app:app --host 0.0.0.0 --port ${PORT:-8080}
