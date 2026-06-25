#!/usr/bin/env bash
# Terrane CI (docker-based runner) — login to the private registry so buildx can push.
# Usage: bash generate-image-repo-secret-docker.sh <registry-host> <username> <password>
set -euo pipefail
REGISTRY_HOST="${1:?registry host}"; USERNAME="${2:?username}"; PASSWORD="${3:?password}"
echo "$PASSWORD" | docker login "$REGISTRY_HOST" -u "$USERNAME" --password-stdin
echo "✓ docker login → $REGISTRY_HOST"
