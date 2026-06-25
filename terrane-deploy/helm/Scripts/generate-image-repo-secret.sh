#!/usr/bin/env bash
# Terrane Helm — create the k8s imagePullSecret `terrane-image-repo-secret` so the cluster can pull
# the private images.
# Usage: bash generate-image-repo-secret.sh <username> <password> <namespace> <registry-url>
# Example: bash generate-image-repo-secret.sh robot 'pass' terrane https://crpi-xxx.cr.aliyuncs.com
set -euo pipefail
USERNAME="${1:?username}"; PASSWORD="${2:?password}"; NS="${3:?namespace}"; URL="${4:?registry url}"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" create secret docker-registry terrane-image-repo-secret \
  --docker-server="$URL" --docker-username="$USERNAME" --docker-password="$PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "✓ secret terrane-image-repo-secret ready in ns/$NS"
