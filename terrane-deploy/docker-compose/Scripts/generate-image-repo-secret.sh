#!/usr/bin/env bash
# Terrane docker-compose — 登录私有镜像仓库(Harbor / 阿里云 ACR),以便 docker compose pull 拉取镜像。
# compose 不像 k8s 用 imagePullSecret,直接 docker login 即可。
# 用法:
#   bash Scripts/generate-image-repo-secret.sh <registry-host> <username> <password>
# 例:
#   bash Scripts/generate-image-repo-secret.sh crpi-ew8juv9423tvogc4.cn-hongkong.personal.cr.aliyuncs.com myuser 'mypass'
set -euo pipefail

REGISTRY_HOST="${1:?registry host, e.g. crpi-xxx.cr.aliyuncs.com}"
USERNAME="${2:?registry username}"
PASSWORD="${3:?registry password}"

echo "$PASSWORD" | docker login "$REGISTRY_HOST" -u "$USERNAME" --password-stdin
echo "✓ 已登录 $REGISTRY_HOST — 现在可 docker compose pull && docker compose up -d"
