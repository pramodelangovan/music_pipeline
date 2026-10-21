# 🎵 Tamil Christian Music Pipeline

A fully automated pipeline to research, download, and organize Tamil Christian music from YouTube.

---

## Overview

This pipeline:
1. **Researches** artists on YouTube (finds albums, playlists, jukeboxes, singles)
2. **Downloads** everything as MP3 with embedded thumbnails and metadata
3. **Splits** jukebox videos into individual tracks (via chapter markers)
4. **Cleans up** filenames, metadata tags, and empty folders

Output lands on your NAS at `/media/disks/nas/music`.

---

## Prerequisites

```bash
# Required binaries
sudo apt install ffmpeg python3 python3-pip

# yt-dlp (keep updated)
pip3 install yt-dlp

# Python packages
pip3 install rich pyyaml mutagen

# Deno (for yt-dlp remote components)
curl -fsSL https://deno.land/install.sh | sh
```

---

## Quick Start

```bash
# 1. Clone / enter project
cd /home/pramod/music_pipeline

# 2. Export cookies from your browser (see Cookie Setup below)
#    and place them at:
cp ~/yt_cookies.txt cookies.txt

# 3. Add an artist to artists.yaml

# 4. Run the full pipeline for one artist
./pipeline.sh "Freddy Joseph"

# 5. Or run all artists
./pipeline.sh all
```

## YouTube Playlist Download Flow

This project now supports a second workflow for direct YT Music playlist URLs without disturbing the artist-based pipeline.

```bash
# Download a playlist as MP3 with max quality and album metadata
python3 scripts/playlist_download.py "https://music.youtube.com/playlist?list=..." \
  --artist "Artist Name" \
  --album "Album Name" \
  --output-dir "/media/disks/nas/music/Playlists"

# Reapply metadata to an already-downloaded folder
python3 scripts/playlist_metadata.py "/media/disks/nas/music/Playlists/Artist Name/Album Name" \
  --artist "Artist Name" \
  --album "Album Name" \
  --cover "/path/to/cover.jpg"

# Or use the wrapper script without changing the existing commands
./pipeline.sh "https://music.youtube.com/playlist?list=..."
```

**What the new flow does:**
- downloads each YouTube track as MP3 with best bitrate available
- embeds album art and ID3 metadata
- tags each file with title, artist, album, track number
- writes files under the selected artist/album folder for later cleanup or import

---

## Cookie Setup

YouTube increasingly requires login cookies for downloads.

### Export from Chrome
1. Install the [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) extension
2. Go to [youtube.com](https://youtube.com) while logged in
3. Click the extension icon → **Export** → save as `cookies.txt`
4. Copy to project: `cp ~/Downloads/cookies.txt /home/pramod/music_pipeline/cookies.txt`

### Export from Firefox
1. Install [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) add-on
2. Go to [youtube.com](https://youtube.com) while logged in
3. Click the add-on → **Current Site** → save as `cookies.txt`
4. Copy to project: `cp ~/Downloads/cookies.txt /home/pramod/music_pipeline/cookies.txt`

### Refreshing Cookies
Cookies expire after ~7 days of inactivity. Signs it's time to refresh:
- Error: `Sign in to confirm you're not a bot`
- Error: `Cookie validation failed`
- Downloads stop unexpectedly

**Refresh steps:** Repeat the export steps above and overwrite `cookies.txt`.

> ⚠️ `cookies.txt` is in `.gitignore` — it will never be committed accidentally.

---

## artists.yaml Guide

```yaml
output_base: /media/disks/nas/music

artists:
  - name: Freddy Joseph              # Full name (used for search + folder)
    aliases:                         # Alternative spellings to try
      - Freddy Joseph Tamil
    known_albums:                    # Albums to explicitly search for
      - Thoothukudi Songs
      - Christmas Special
    fetch_singles: true              # Include standalone songs
    fetch_unknown_albums: true       # Auto-discover unlisted albums
```

**Fields:**
| Field | Type | Description |
|---|---|---|
| `name` | string | Primary artist name |
| `aliases` | list | Alternative names to search |
| `known_albums` | list | Albums guaranteed to be searched |
| `fetch_singles` | bool | Include singles (default: true) |
| `fetch_unknown_albums` | bool | Auto-discover albums (default: true) |

---

## config.yaml Guide

```yaml
paths:
  cookies: "cookies.txt"      # Path to cookies file (relative to project)
  output_base: "/media/disks/nas/music"
  logs: "logs"
  deno: "/home/pramod/.deno/bin"

yt_dlp:
  audio_format: "mp3"
  audio_quality: 0            # 0 = best quality
  retries: 5
  sleep_interval: 3           # Seconds between requests
  max_sleep_interval: 8

delays:
  between_albums: 40          # Seconds between album downloads
  between_singles: 10
  between_artists: 60

error_handling:
  skip_unavailable: true      # Skip deleted/private videos
  max_errors_per_artist: 10   # Stop artist after N errors
  retry_on_bot_detection: true
  retry_delay: 300            # Wait 5 min if bot-detected
  fail_on_cookie_error: true  # Stop if cookies invalid

notifications:
  log_level: "INFO"           # DEBUG / INFO / WARNING / ERROR
  save_error_report: true     # Write JSON error report per artist
  show_tui: true              # Rich terminal progress UI

cleanup:
  delete_empty_folders: true
  fix_filenames: true
  fix_metadata: true
  delete_jukebox_if_split: true
  min_split_tracks: 3         # Tracks needed before deleting jukebox
```

---

## Running the Pipeline

### Full pipeline
```bash
./pipeline.sh "Artist Name"   # Single artist
./pipeline.sh all             # All artists in artists.yaml
./pipeline.sh all --no-tui    # Disable rich TUI (for logs/CI)
```

### Individual steps
```bash
# Research only (generates download_plan.yaml)
python3 scripts/research.py "Paul Thangiah"

# Download only (reads download_plan.yaml)
python3 scripts/download.py "Paul Thangiah"
python3 scripts/download.py "Paul Thangiah" --no-tui

# Split jukebox chapters
python3 scripts/split_chapters.py "Paul Thangiah"

# Cleanup filenames + metadata
python3 scripts/cleanup.py
python3 scripts/cleanup.py /path/to/specific/dir
```

---

## TUI Guide

When `show_tui: true` in config.yaml, download.py shows a live progress display:

```
🎵 Tamil Christian Music Downloader
┌─────────────────────────┬──────────────┬─────────────┬───────┬───────────────────────────────────────┐
│ Artist                  │ Status       │ Downloaded  │ Errors│ Current Track                         │
├─────────────────────────┼──────────────┼─────────────┼───────┼───────────────────────────────────────┤
│ Freddy Joseph           │ done         │ 23          │ 0     │                                       │
│ Paul Thangiah           │ downloading  │ 12          │ 1     │ En Uyir Nadane - Official Video        │
│ Johnson Jayaraj         │ pending      │ 0           │ 0     │                                       │
└─────────────────────────┴──────────────┴─────────────┴───────┴───────────────────────────────────────┘
⠿ Paul Thangiah  ████████████░░░░░░░░░░  60%  eta 0:04:12
```

**Columns:**
- **Artist** — name from artists.yaml
- **Status** — `pending` / `downloading` / `done` / `error`
- **Downloaded** — successful downloads so far
- **Errors** — failed/skipped items
- **Current Track** — track being downloaded right now

Disable with `--no-tui` flag or `notifications.show_tui: false` in config.yaml.

---

## Error Reference

| Error Type | Cause | Fix |
|---|---|---|
| `bot_detected` | YouTube wants human verification | Refresh cookies; pipeline waits 5 min and retries |
| `unavailable` | Video deleted, private, or terminated | Skipped automatically |
| `copyright` | Geo-blocked or copyright claim | Skipped automatically |
| `network` | Connection timeout or refused | Retried with exponential backoff |
| `unknown` | Other yt-dlp error | Check logs for details |

Error reports saved to `logs/errors_{Artist}_{timestamp}.json`.

---

## Troubleshooting

**`cookies.txt not found`**
→ Export cookies from your browser (see Cookie Setup above)

**`Cookie validation failed — cookies expired`**
→ Re-export cookies from YouTube while logged in

**Downloads stop after a few tracks**
→ Bot detection triggered. Pipeline waits 5 minutes and retries. If persistent, refresh cookies.

**`yt-dlp: command not found`**
→ `pip3 install yt-dlp` or check PATH

**`deno: command not found`**
→ Check `paths.deno` in config.yaml points to your deno installation

**Metadata not being written**
→ `pip3 install mutagen`

**TUI not showing**
→ `pip3 install rich` or set `show_tui: false` in config.yaml

---

## Adding New Artists

1. Open `artists.yaml`
2. Add entry under `artists:`:
   ```yaml
   - name: New Artist Name
     aliases:
       - Alternative Name
     known_albums:
       - Album Title 1
     fetch_singles: true
     fetch_unknown_albums: true
   ```
3. Run research: `python3 scripts/research.py "New Artist Name"`
4. Review `download_plan.yaml` — remove unwanted items if needed
5. Download: `python3 scripts/download.py "New Artist Name"`

---

## File Structure

```
music_pipeline/
├── README.md              ← This file
├── AGENT_PROMPT.md        ← Prompt for AI-assisted operation
├── artists.yaml           ← Artist list + config
├── config.yaml            ← Runtime settings
├── cookies.txt            ← YouTube auth cookies (gitignored)
├── download_plan.yaml     ← Generated: what to download
├── pipeline.sh            ← Master runner script
├── scripts/
│   ├── research.py        ← YouTube search → download_plan.yaml
│   ├── download.py        ← Download MP3s with rich TUI
│   ├── cleanup.py         ← Fix filenames + metadata
│   └── split_chapters.py  ← Split jukebox by chapter markers
└── logs/
    ├── research_*.json    ← Research results per artist
    ├── download_*.log     ← Download logs
    └── errors_*.json      ← Error reports per artist
```

---

## Refreshing Cookies (Detailed Steps)

### Chrome
1. Open Chrome and log into [youtube.com](https://youtube.com)
2. Click the **Get cookies.txt LOCALLY** extension icon
3. Choose **Export** → **Current Site only**
4. Save the file
5. `cp ~/Downloads/youtube.com_cookies.txt /home/pramod/music_pipeline/cookies.txt`

### Firefox
1. Open Firefox and log into [youtube.com](https://youtube.com)  
2. Click the **cookies.txt** add-on icon
3. Select **For this site** → download
4. `cp ~/Downloads/cookies.txt /home/pramod/music_pipeline/cookies.txt`

After replacing cookies.txt, the pipeline will validate them automatically on next run.
