#!/bin/bash
# Tamil Christian Music Download Pipeline
# Usage: ./pipeline.sh [artist_name|all] [--no-tui]
# Steps: research → download → split_chapters → cleanup

set -e
ARTIST=${1:-all}
NO_TUI=${2:-}
PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PIPELINE_DIR"

if [[ "$ARTIST" =~ ^https?:// ]]; then
  echo ""
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║   YouTube Playlist Download Flow                    ║"
  echo "║   URL: $ARTIST"
  echo "╚══════════════════════════════════════════════════════╝"
  echo ""
  python3 scripts/playlist_download.py "$ARTIST"
  exit 0
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Tamil Christian Music Pipeline                     ║"
echo "║   Artist: $ARTIST"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

echo "=== Step 1: Research ==="
python3 scripts/research.py "$ARTIST"
echo ""

echo "=== Step 2: Download ==="
python3 scripts/download.py "$ARTIST" $NO_TUI
echo ""

echo "=== Step 3: Split Chapters ==="
python3 scripts/split_chapters.py "$ARTIST"
echo ""

echo "=== Step 4: Cleanup ==="
python3 scripts/cleanup.py
echo ""

echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✓ Pipeline complete!                               ║"
echo "╚══════════════════════════════════════════════════════╝"
