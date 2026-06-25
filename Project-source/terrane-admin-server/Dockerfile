# Terrane API (frontend) — Python 3.13 + uv. Pure CPU (incl. Terrane Parse: PyMuPDF/Office, no GPU).
FROM python:3.13-slim AS base

# Runtime system dependencies (PyMuPDF wheel is self-contained, nothing extra needed; add ca/locale)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# Install dependencies first (leverage layer caching)
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY . .

EXPOSE 43003
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:43003/livez || exit 1
CMD ["python", "main.py"]
