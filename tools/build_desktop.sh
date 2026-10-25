#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-desktop.txt

pyinstaller --clean --noconfirm apps/desktop/music_pipeline_desktop.spec

echo "Build finished"
echo "Output: dist/MusicPipelineDesktop/"
