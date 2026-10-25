#!/usr/bin/env bash
# Installs Deno and ffmpeg on Linux (and macOS via Homebrew).
set -euo pipefail

have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
if [ "$(id -u)" -ne 0 ] && have sudo; then SUDO="sudo"; fi

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

install_ffmpeg
install_deno

export PATH="$HOME/.deno/bin:$PATH"
echo
ffmpeg -version | head -n 1
deno --version | head -n 1
echo
echo 'Ensure Deno is on PATH: export PATH="$HOME/.deno/bin:$PATH"'
