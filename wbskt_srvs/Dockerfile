FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps.
#   libpq5       : runtime for psycopg2
#   libpq-dev    : only needed if psycopg2 (not psycopg2-binary) is used.
#   gcc          : only needed for source builds. Kept in a separate layer so
#                  it can be dropped later if you want a slimmer image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Python deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source.
# The websocket-service needs the Django project so it can import
# cb_trades.tasks (strategy_s1 / redis_store_price). If your Django project
# lives elsewhere in the repo, adjust the COPY paths or mount it via compose.
COPY . .

# Non-root user.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["python", "ws_service.py"]