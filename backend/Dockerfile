# Estima3D API. docker-compose.yml builds it with the same SOURCE_REVISION /
# BUILD_ID as the frontend image (see docs/DOCKER.md).
FROM python:3.12.10-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# LightGBM's wheel links the system OpenMP runtime; nothing else is native
# beyond what the wheels bundle (PyMuPDF renders PDFs with its own fonts).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 appuser && chown appuser:appuser /app
# Application code and its immutable assets only: tests, scripts and reports
# stay out of the runtime image, private runtime data is in .dockerignore.
COPY --chown=appuser:appuser app.py config.py docker-entrypoint.sh ./
COPY --chown=appuser:appuser routers ./routers
COPY --chown=appuser:appuser services ./services
COPY --chown=appuser:appuser database ./database
# training/ is the seed for a persistent disk (see docker-entrypoint.sh, which
# also drops root before starting the app). Copied straight to its seed path:
# renaming it in a later layer would store all 420 MB twice.
COPY --chown=appuser:appuser training ./training.image
RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh

# Last, so a new commit does not invalidate the dependency layers.
ARG SOURCE_REVISION=unknown
ARG BUILD_ID=unknown
ENV APP_SOURCE_REVISION=${SOURCE_REVISION} \
    APP_BUILD_ID=${BUILD_ID}
LABEL org.opencontainers.image.title="estima3d-api" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${BUILD_ID}"

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["sh", "-c", "exec uvicorn app:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --log-level ${LOG_LEVEL:-info}"]

# Reproducible test environment: the runtime image plus pytest, the tests and
# the scripts / reports they read.
# `docker compose --profile test run --rm backend-tests`; never deployed.
FROM runtime AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=appuser:appuser . .
# The context's copy of the entrypoint may have CRLF line ends (Windows checkout).
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--continue-on-collection-errors"]

# The default (last) stage, so builds without --target (render.yaml) deploy the
# runtime image, never the test one.
FROM runtime AS production
