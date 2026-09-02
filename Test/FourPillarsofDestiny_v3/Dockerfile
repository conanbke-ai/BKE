FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PUBLIC_DEPLOYMENT=1 \
    PERSIST_USER_DATA=0 \
    EXTERNAL_SOURCE_ENABLED=0 \
    AI_ENABLED=0 \
    BUILD_AUTO_MATCHES=0 \
    HEADLESS=1 \
    DEBUG=0 \
    STATE_DIR=/var/data \
    DATA_DIR=/var/data/data \
    BROWSER_PROFILE_DIR=/var/data/browser-profile

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/data/data /var/data/browser-profile \
    && chown -R appuser:appuser /var/data /ms-playwright

COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-900} --graceful-timeout 30 --access-logfile - --error-logfile - wsgi:app"]
