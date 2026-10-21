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
