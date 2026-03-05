# ── Build stage ────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --pre -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Hosted agents use PORT=8088 by default; Foundry injects its own PORT.
# For local testing / ACA fallback, default to 8088.
ENV PORT=8088
EXPOSE 8088

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

# When PORT is set the app auto-detects server mode
CMD ["python", "app.py", "--server"]
