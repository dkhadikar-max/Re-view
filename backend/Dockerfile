# Build context = repository root (Railway: Dockerfile path = backend/Dockerfile)
# Do NOT also set Root Directory to backend, or paths will break.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
COPY backend/scripts ./scripts
COPY backend/sample_reservations.csv .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${PORT:-8000}/ready || exit 1

# CTO P1 (follow-up to #56): migrate-and-verify gate runs before uvicorn.
# If the migration chain is branched, a migration fails, or the DB doesn't
# land exactly on head, this exits non-zero and the container fails to
# start — Railway keeps serving the last healthy deployment instead of
# promoting a broken one. schema_patches.py (still invoked from main.py's
# lifespan) stays as a temporary safety net; see scripts/migrate_and_verify.py.
CMD ["sh", "-c", "python -m scripts.migrate_and_verify && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
