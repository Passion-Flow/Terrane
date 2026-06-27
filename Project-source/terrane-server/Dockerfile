# Terrane API (frontend) -- Python 3.13 + uv. CPU-only (incl. Terrane Parse: pypdfium2/pdfplumber/RapidOCR/Office, no GPU).
FROM python:3.13-slim AS base

# Runtime system dependencies:
#  - ca/curl + ffmpeg (video parsing: scene/keyframe + audio-track extraction via PySceneDetect/ffmpeg)
#  - libgl1 + libglib2.0-0: OpenCV runtime libs. rapidocr-onnxruntime pulls the FULL opencv-python, whose
#    cv2 imports libGL.so.1 / libglib at load time; without these the container crashes on `import cv2`.
#  - libreoffice (headless) + CJK fonts: Office (docx/xlsx/pptx) -> PDF -> per-page WebP layout preview
# At build time, switch to the Aliyun Debian mirror (reliable direct connection / faster; affects the build stage only, the final image carries no apt-source difference).
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    apt-get -o Acquire::Retries=8 update && \
    apt-get -o Acquire::Retries=8 -o Acquire::http::Pipeline-Depth=0 install -y --no-install-recommends \
        ca-certificates curl ffmpeg \
        libgl1 libglib2.0-0 \
        libreoffice-impress libreoffice-writer libreoffice-calc \
        fonts-noto-cjk fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
# UV_DEFAULT_INDEX: at build time use the Aliyun PyPI mirror (reliable direct connection / faster; affects the build only, the final image carries no pip source).
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/

# Install dependencies first (leverage layer caching)
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY . .

EXPOSE 43001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:43001/livez || exit 1
CMD ["python", "main.py"]
