#!/usr/bin/env bash
# Sets up Music Pipeline on Linux (and macOS via Homebrew):
#   1. system packages: python3 (+venv/pip), ffmpeg, Deno
#   2. a .venv in the project root (created only if missing)
#   3. every Python requirement (requirements-desktop.txt, which includes requirements.txt)
#
# Usage: bash tools/setup.sh [--deps-only]
#   --deps-only  only ffmpeg and Deno (used by the app itself when it finds them missing)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPS_ONLY=0
[ "${1:-}" = "--deps-only" ] && DEPS_ONLY=1

have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
if [ "$(id -u)" -ne 0 ] && have sudo; then SUDO="sudo"; fi

install_python() {
  if have python3 && python3 -c "import venv, ensurepip" >/dev/null 2>&1; then
    echo "python3 (with venv/pip) already installed"; return
  fi
  echo "Installing python3, venv and pip..."
  if have apt-get; then
    $SUDO apt-get update && $SUDO apt-get install -y python3 python3-venv python3-pip
  elif have dnf; then
    $SUDO dnf install -y python3 python3-pip
  elif have pacman; then
    $SUDO pacman -S --noconfirm python python-pip
  elif have zypper; then
    $SUDO zypper install -y python3 python3-pip
  elif have apk; then
    $SUDO apk add python3 py3-pip
  elif have brew; then
    brew install python
  else
    echo "No supported package manager found; install python3 manually." >&2
    exit 1
  fi
}

install_ffmpeg() {
  if have ffmpeg; then echo "ffmpeg already installed"; return; fi
  echo "Installing ffmpeg..."
  if have apt-get; then
    $SUDO apt-get update && $SUDO apt-get install -y ffmpeg
  elif have dnf; then
    $SUDO dnf install -y ffmpeg-free || $SUDO dnf install -y ffmpeg
  elif have pacman; then
    $SUDO pacman -S --noconfirm ffmpeg
  elif have zypper; then
    $SUDO zypper install -y ffmpeg
  elif have apk; then
    $SUDO apk add ffmpeg
  elif have brew; then
    brew install ffmpeg
  else
    echo "No supported package manager found; install ffmpeg manually." >&2
    exit 1
  fi
}

install_deno() {
  export PATH="$HOME/.deno/bin:$PATH"
  if have deno; then echo "deno already installed"; return; fi
  echo "Installing Deno..."
  if have brew && [ "$(uname -s)" = "Darwin" ]; then
    brew install deno
    return
  fi
  have curl || { echo "curl is required to install Deno" >&2; exit 1; }
  have unzip || { echo "unzip is required to install Deno" >&2; exit 1; }
  curl -fsSL https://deno.land/install.sh | sh -s -- -y
}

setup_venv() {
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    echo ".venv already exists"
  else
    echo "Creating .venv..."
    python3 -m venv "$ROOT_DIR/.venv"
  fi
  echo "Installing Python requirements..."
  "$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip
  "$ROOT_DIR/.venv/bin/python" -m pip install -r "$ROOT_DIR/requirements-desktop.txt"
}

[ "$DEPS_ONLY" -eq 0 ] && install_python
install_ffmpeg
install_deno
[ "$DEPS_ONLY" -eq 0 ] && setup_venv

export PATH="$HOME/.deno/bin:$PATH"
echo
ffmpeg -version | head -n 1
deno --version | head -n 1
if [ "$DEPS_ONLY" -eq 0 ]; then
  "$ROOT_DIR/.venv/bin/python" --version
  echo
  echo "Setup complete. Activate the environment with: source .venv/bin/activate"
fi
echo 'Ensure Deno is on PATH: export PATH="$HOME/.deno/bin:$PATH"'
