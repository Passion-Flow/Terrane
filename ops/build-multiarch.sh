#!/usr/bin/env bash
# Terrane 多架构镜像(amd64 + arm64/鲲鹏飞腾)。基础镜像均多架构,buildx 一键双架构。
set -euo pipefail
REGISTRY="${REGISTRY:?设置 REGISTRY}"; TAG="${TAG:-1.0.0}"; PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
SRC="$(dirname "$0")/../Project-source"
docker buildx create --use --name terrane-builder 2>/dev/null || docker buildx use terrane-builder
for svc in terrane-server terrane-admin-server terrane-gateway terrane-web terrane-admin-web; do
  echo ">> buildx $svc ($PLATFORMS)"
  docker buildx build --platform "$PLATFORMS" -t "$REGISTRY/$svc:$TAG" --push "$SRC/$svc"
done
echo "DONE 多架构镜像已推送"
