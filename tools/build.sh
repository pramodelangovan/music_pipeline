#!/usr/bin/env bash
# Music Pipeline build/deploy entry point.
#
# Usage: bash tools/build.sh <target>
#   web        build the Docker images and start the web app (API + UI) with Docker Compose
#   web-build  build the Docker images and package them as dist/docker.tar.gz (plus a compose file)
#   desktop    build the desktop app with PyInstaller into dist/MusicPipeline/
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-1}"
}

need_docker() {
  command -v docker >/dev/null 2>&1 || { echo "Docker is not installed or not on PATH." >&2; exit 1; }
  docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required (docker compose)." >&2; exit 1; }
  docker info >/dev/null 2>&1 || { echo "The Docker daemon is not running." >&2; exit 1; }
}

# Compose bind-mounts cookies.txt; a missing file would be created as a directory.
prepare_runtime_files() {
  mkdir -p downloads logs
  [ -e cookies.txt ] || : > cookies.txt
}

build_web() {
  need_docker
  prepare_runtime_files
  docker compose up -d --build
  echo
  echo "Music Pipeline web is running."
  echo "  UI:  http://localhost:3000"
  echo "  API: http://localhost:8000"
  echo "Stop with: docker compose down"
}

package_web() {
  need_docker
  docker compose build
  rm -rf dist/docker.tar.gz dist/docker-compose.yml dist/cookies.txt
  mkdir -p dist
  docker save music-pipeline-api:latest music-pipeline-web:latest | gzip > dist/docker.tar.gz

  # The packaged compose file uses the loaded images, so drop the build sections.
  awk '
    /^    build:/ { skip = 1; next }
    skip && /^      / { next }
    { skip = 0; print }
  ' docker-compose.yml > dist/docker-compose.yml
  : > dist/cookies.txt

  echo
  echo "Docker package ready in dist/:"
  echo "  docker.tar.gz, docker-compose.yml, cookies.txt"
  echo "On the target machine: docker load -i docker.tar.gz && docker compose up -d"
}

build_desktop() {
  [ -x .venv/bin/python ] || bash "$ROOT_DIR/tools/setup.sh"
  .venv/bin/python -m PyInstaller --clean --noconfirm apps/desktop/music_pipeline_desktop.spec
  echo
  echo "Desktop build finished."
  echo "Output: dist/MusicPipeline/"
}

case "${1:-}" in
  web) build_web ;;
  web-build) package_web ;;
  desktop) build_desktop ;;
  -h|--help) usage 0 ;;
  *) usage 1 ;;
esac
