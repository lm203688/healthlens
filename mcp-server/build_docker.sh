#!/usr/bin/env bash
# Build and optionally push the HealthLens MCP Docker image.
# Run from the repo root (not from mcp-server/).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-lm203688/healthlens-mcp}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PUSH="${PUSH:-0}"

cd "$REPO_ROOT"

echo "==> Building ${IMAGE_NAME}:${IMAGE_TAG}"
echo "    Build context: $REPO_ROOT"
echo "    Dockerfile:    mcp-server/Dockerfile"
docker build \
  -f mcp-server/Dockerfile \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  .

echo "==> Verifying image"
docker run --rm --entrypoint "" "${IMAGE_NAME}:${IMAGE_TAG}" \
  python -m healthlens_agent.mcp_server --demo | head -20

if [[ "$PUSH" == "1" ]]; then
  echo "==> Pushing ${IMAGE_NAME}:${IMAGE_TAG} to Docker Hub"
  docker push "${IMAGE_NAME}:${IMAGE_TAG}"
else
  echo "==> Skipping push. Set PUSH=1 to publish to Docker Hub."
fi
