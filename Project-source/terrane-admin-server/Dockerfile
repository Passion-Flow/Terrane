# Terrane API（前台）—— Python 3.13 + uv。纯 CPU(含 Terrane Parse:PyMuPDF/Office,无 GPU)。
FROM python:3.13-slim AS base

# 运行期系统依赖(PyMuPDF wheel 自带,无需额外;补 ca/locale)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# 先装依赖(利用层缓存)
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY . .

EXPOSE 43003
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:43003/livez || exit 1
CMD ["python", "main.py"]
