# 🎵 YouTube Music Downloader

A generic, open-ended pipeline for downloading YouTube music playlists as MP3 files, organizing them into folders, and tagging the output with album, artist, track, and artwork metadata.

---

## Overview

This project supports a simple workflow:

1. Accept a YouTube playlist URL
2. Download each track as MP3
3. Preserve highest available audio quality
4. Embed cover art and ID3 metadata
5. Save the library into a clean folder structure

It also keeps the older artist-driven research/download flow intact for projects that still use that pattern.

---

## What the project does

- downloads YouTube playlist items as MP3
- writes title, artist, album, and track number tags
- embeds cover art into the MP3 files
- organizes output under artist/album folders
- supports override metadata for specific playlists
- creates log files for playlist runs and metadata writes

---

## Prerequisites

```bash
# system packages
sudo apt update
sudo apt install ffmpeg python3 python3-pip

# python packages
pip3 install -r requirements.txt

# optional but recommended for YouTube challenge solving
auto-install deno
curl -fsSL https://deno.land/install.sh | sh
```

Make sure your shell has Deno on PATH:

```bash
export PATH="$HOME/.deno/bin:$PATH"
```

---

## Quick start

### 1) Export YouTube cookies
YouTube often requires login cookies for access.

For Chrome:

1. Install the Chrome extension: Get cookies.txt LOCALLY
2. Open YouTube while signed in
3. Click the extension and export the cookie file
4. Save it as `cookies.txt` in the project root

Example:

```bash
cp ~/Downloads/cookies.txt /home/Workspace/music_pipeline/cookies.txt
```

### 2) Run a playlist download

```bash
cd /home/Workspace/music_pipeline
./pipeline.sh "https://music.youtube.com/playlist?list=YOUR_PLAYLIST_ID"
```

### 3) Or use the direct downloader command

```bash
python3 scripts/playlist_download.py "https://music.youtube.com/playlist?list=YOUR_PLAYLIST_ID" \
  --artist "Artist Name" \
  --album "Album Name" \
  --output-dir "/media/disks/nas/music/Playlists"
```

### 4) Reapply metadata to an existing folder

```bash
python3 scripts/playlist_metadata.py "/media/disks/nas/music/Playlists/Artist Name/Album Name" \
  --artist "Artist Name" \
  --album "Album Name" \
  --cover "/path/to/cover.jpg"
```

---

## Playlist override metadata

For film or playlist-specific music where YouTube data is noisy or incomplete, the project supports explicit overrides via [playlist_metadata.yaml](playlist_metadata.yaml).

Example:

```yaml
playlists:
  - id: "OLAK5uy_lHWX8XhioMBQjHfDE0DurDjhXV3WdY454"
    name: "Jailer 2 Soundtrack"
    artist: "Anirudh Ravichander"
    album: "Jailer 2"
    tracks:
      - title: "Ala Bolelo"
        artist: "Anirudh Ravichander"
        album: "Jailer 2"
```

This lets the script prefer the correct album and artist values instead of guessing from generic metadata sources.

---

## File structure

```text
music_pipeline/
├── README.md
├── requirements.txt
├── config.yaml
├── cookies.txt
├── playlist_metadata.yaml
├── pipeline.sh
├── scripts/
│   ├── download.py
│   ├── research.py
│   ├── cleanup.py
│   ├── split_chapters.py
│   ├── playlist_download.py
│   ├── playlist_metadata.py
│   ├── playlist_override_metadata.py
│   ├── playlist_utils.py
│   └── metadata_enricher.py
├── logs/
│   ├── playlist_download_*.log
│   ├── playlist_summary_*.json
│   └── ...
└── tests/
    ├── test_playlist_metadata.py
    └── test_metadata_enricher.py
```

---

## Important notes

### Cookies
YouTube can block access without valid cookies. If you see bot-check errors, refresh your cookies and retry.

### JS challenge handling
Some YouTube videos require a JavaScript challenge solver. The project includes Deno-based support for this path.

### Metadata quality
For movie and regional music, playlist-level metadata overrides are usually more accurate than generic open metadata APIs. Use the override file when you already know the correct artist and album.

---

## Troubleshooting

### `Sign in to confirm you're not a bot`
Refresh the cookies file and retry.

### `Requested format is not available`
Install the required JS runtime support and ensure Deno is on PATH.

### `Metadata not appearing`
Check the MP3 tag writing logs in the `logs/` folder and verify `mutagen` is installed.

### `ffmpeg not found`
Install it with:

```bash
sudo apt install ffmpeg
```

---

## Typical usage patterns

### Generic playlist download
```bash
./pipeline.sh "https://music.youtube.com/playlist?list=..."
```

### Playlist with explicit artist/album
```bash
python3 scripts/playlist_download.py "https://music.youtube.com/playlist?list=..." \
  --artist "Artist Name" \
  --album "Album Name"
```

### Old-style artist-based workflow
```bash
./pipeline.sh "Artist Name"
```

---

This project is intentionally generic and can be used for YouTube music playlists across many genres, not just one specific catalog or region.

---

## Queue Downloader + React UI

This repository now includes a queue-based downloader service and a React Material UI.

### Features

- supports single URL download as `audio` or `video`
- supports playlist URL expansion into per-track queue jobs
- uses two worker agents:
  - Queue Agent: resolves incoming URLs and expands playlists into individual jobs
  - Download Agent: downloads queued jobs one-by-one with a configurable time gap
- supports multi-row queue input from UI
- supports cookies upload from a Settings tab (updates `cookies.txt`)
- tracks all queue jobs in SQLite (`logs/downloads.db`)
- includes a History page in UI for completed and past jobs
- includes a `Clear Last Downloads` action that clears completed items from the Queue view while keeping history

### Tracking database

- Database file: `logs/downloads.db`
- Main table: `downloads`
- Status values: `queued`, `downloading`, `done`, `failed`
- Queue page reads active/non-cleared rows
- History page reads full history, including previously cleared rows

### Run with Docker Compose

```bash
cd /home/Workspace/music_pipeline
docker compose up --build
```

Services:

- UI: `http://localhost:3000`
- API: `http://localhost:8000`

Volumes:

- `./downloads:/app/downloads` (downloaded media)
- `./logs:/app/logs` (runtime logs and settings)
- `./cookies.txt:/app/cookies.txt` (cookie updates from UI)
- `./config.yaml:/app/config.yaml` (base config)

### Run without Docker

Backend:

```bash
cd /home/Workspace/music_pipeline
pip3 install -r requirements.txt
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd /home/Workspace/music_pipeline/apps/web
npm install
npm run dev
```

Open the frontend and queue one or more rows with URL + media type + target folder.

---

## Desktop App (PySide6)

A desktop client is included. It runs the download queue in-process (no API server needed) using the same shared service, `core/queue_manager.py`, that the HTTP API wraps:

- Queue tab: add multiple URL rows (audio/video + folder), queue downloads, clear last downloads
- Settings tab: queue gap, cookies import
- History tab: full SQLite-backed download history

### Desktop files

- App entry: `apps/desktop/main.py`
- Shared queue/download service: `core/queue_manager.py` (used by both desktop and `apps/api/main.py`)
- Styling (QSS): `apps/desktop/resources/style.qss`
- PyInstaller spec: `apps/desktop/music_pipeline_desktop.spec`

### Run desktop app (dev)

```bash
cd /home/Workspace/music_pipeline
pip3 install -r requirements-desktop.txt
python3 apps/desktop/main.py
```

### Build Windows EXE with PyInstaller

Build on Windows (recommended):

```bat
cd C:\path\to\music_pipeline
scripts\build_desktop.bat
```

Output:

- `dist\MusicPipelineDesktop\MusicPipelineDesktop.exe`

Linux/macOS build helper (non-EXE targets):

```bash
cd /home/Workspace/music_pipeline
bash scripts/build_desktop.sh
```
