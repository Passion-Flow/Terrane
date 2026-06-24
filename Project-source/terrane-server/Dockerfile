# Terrane API（前台）—— Python 3.13 + uv。纯 CPU(含 Terrane Parse:PyMuPDF/Office,无 GPU)。
FROM python:3.13-slim AS base

# 运行期系统依赖:
#  - ca/curl + ffmpeg(视频解析抽帧/抽音轨;PyMuPDF wheel 自带其余)
#  - libreoffice(无界面) + 中日韩字体:Office(docx/xlsx/pptx)→PDF→逐页 WebP 版面预览
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl ffmpeg \
        libreoffice-impress libreoffice-writer libreoffice-calc \
        fonts-noto-cjk fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# 先装依赖(利用层缓存)
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY . .

EXPOSE 43001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:43001/livez || exit 1
CMD ["python", "main.py"]
