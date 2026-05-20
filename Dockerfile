FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web_app/ ./web_app/
COPY vendor/ ./vendor/
COPY *.py ./

RUN mkdir -p web_app/cache_v19 web_app/snapshots data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["gunicorn", \
     "--worker-class", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", \
     "--workers", "1", \
     "--threads", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "web_app.app:app"]
