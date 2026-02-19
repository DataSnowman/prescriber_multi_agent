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

# Azure Container Apps injects PORT (default 8080)
ENV PORT=8080
EXPOSE 8080

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# When PORT is set the app auto-detects server mode
CMD ["python", "app.py", "--server"]
