#!/bin/sh
# Build the Estima3D backend and frontend images together from this checkout
# with one SOURCE_REVISION / BUILD_ID (see scripts/docker-build.ps1 and
# docs/DOCKER.md). Usage: scripts/docker-build.sh [--up]
set -eu
cd "$(dirname "$0")/.."

SOURCE_REVISION=$(git rev-parse HEAD)
short=$(printf %.7s "$SOURCE_REVISION")
# Tracked changes only: untracked runtime files are outside the build context.
if [ -n "$(git status --porcelain --untracked-files=no -- backend frontend docker-compose.yml)" ]; then
  BUILD_ID="$short-dirty-$(date -u +%Y%m%d%H%M%S)"
else
  BUILD_ID=$short
fi
export SOURCE_REVISION BUILD_ID IMAGE_TAG=current

echo "Building estima3d-api and estima3d-web: revision $SOURCE_REVISION, build $BUILD_ID"
docker compose build backend frontend
[ "${1:-}" = "--up" ] && docker compose up -d
echo "Built $BUILD_ID. Images: estima3d-api:$BUILD_ID, estima3d-web:$BUILD_ID (also :current)."
