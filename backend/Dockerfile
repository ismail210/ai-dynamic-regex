FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 appuser && chown appuser:appuser /app
COPY --chown=appuser:appuser . .
# training/ becomes the seed for a persistent disk (see docker-entrypoint.sh),
# which also drops root before starting the app.
RUN mv training training.image \
    && sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["sh", "-c", "uvicorn app:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --log-level ${LOG_LEVEL:-info}"]
