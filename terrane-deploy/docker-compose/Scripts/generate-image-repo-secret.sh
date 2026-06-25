#!/usr/bin/env bash
# Terrane docker-compose — log in to the private image registry (Harbor / Aliyun ACR) so that
# `docker compose pull` can fetch the images.
# Unlike k8s, compose does not use an imagePullSecret — a plain `docker login` is enough.
# Usage:
#   bash Scripts/generate-image-repo-secret.sh <registry-host> <username> <password>
# Example:
#   bash Scripts/generate-image-repo-secret.sh crpi-ew8juv9423tvogc4.cn-hongkong.personal.cr.aliyuncs.com myuser 'mypass'
set -euo pipefail

REGISTRY_HOST="${1:?registry host, e.g. crpi-xxx.cr.aliyuncs.com}"
USERNAME="${2:?registry username}"
PASSWORD="${3:?registry password}"

echo "$PASSWORD" | docker login "$REGISTRY_HOST" -u "$USERNAME" --password-stdin
echo "✓ Logged in to $REGISTRY_HOST — you can now run: docker compose pull && docker compose up -d"
