#!/usr/bin/env bash
# Terrane CI (k8s deploy target) — create/refresh the imagePullSecret `terrane-image-repo-secret`
# in the target namespace, so the cluster can pull the private images.
# Usage: bash generate-image-repo-secret-k8s.sh <username> <password> <namespace> <registry-url>
set -euo pipefail
USERNAME="${1:?username}"; PASSWORD="${2:?password}"; NS="${3:?namespace}"; URL="${4:?registry url, e.g. https://crpi-xxx.cr.aliyuncs.com}"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" create secret docker-registry terrane-image-repo-secret \
  --docker-server="$URL" --docker-username="$USERNAME" --docker-password="$PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "✓ secret terrane-image-repo-secret ready in ns/$NS"
