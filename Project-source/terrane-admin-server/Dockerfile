# Terrane Admin API — Python 3.13 + uv. Pure CPU, no GPU. (No document-parse engine here: the admin server
# does not import app.services.parse, so it needs none of the vision/OpenCV/ffmpeg runtime libs.)
FROM python:3.13-slim AS base

# Runtime system dependencies (admin has no parse/vision deps; just ca-certificates + curl for healthcheck).
# At build time switch to the Aliyun Debian mirror (faster/reliable in CN; build stage only, final image carries no apt-source diff).
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    apt-get -o Acquire::Retries=8 update && \
    apt-get -o Acquire::Retries=8 -o Acquire::http::Pipeline-Depth=0 install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
# UV_DEFAULT_INDEX: at build time use the Aliyun PyPI mirror (reliable/faster in CN; build only, final image carries no pip source).
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/

# Install dependencies first (leverage layer caching)
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY . .

EXPOSE 43003
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:43003/livez || exit 1
CMD ["python", "main.py"]
