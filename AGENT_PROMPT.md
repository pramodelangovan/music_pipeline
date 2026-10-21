# AGENT_PROMPT.md — AI Agent Instructions for Tamil Christian Music Pipeline

Copy and paste this prompt to an AI agent to run the full pipeline end-to-end.

---

## Task: Download Tamil Christian Music

You are running on or have SSH access to **Artemis** server.

**Server:** 192.168.1.120  
**User:** pramod  
**Sudo password:** {{SUDO_PASSWORD}}  
**Pipeline location:** `/home/pramod/music_pipeline/`

## Environment

- yt-dlp: `/usr/local/bin/yt-dlp`
- ffmpeg: `/usr/bin/ffmpeg`
- deno: `/home/pramod/.deno/bin/deno`
- cookies: `/home/pramod/yt_cookies.txt`
- output: `/media/disks/nas/music/`

## Step-by-Step Instructions

### Step 1: Verify environment
```bash
cd /home/pramod/music_pipeline
ls scripts/
python3 -c "import yaml, mutagen; print('deps ok')"
ls /home/pramod/yt_cookies.txt && echo "cookies ok"
```

### Step 2: Run the pipeline for a specific artist
```bash
./pipeline.sh "Paul Thangiah"
```

Or for all artists (takes hours, run in screen/tmux):
```bash
screen -S music_pipeline
./pipeline.sh all
# Ctrl+A D to detach
```

### Step 3: Individual steps if needed
```bash
# Research only (generates download_plan.yaml)
python3 scripts/research.py "Paul Thangiah"

# Check what was found
cat download_plan.yaml | python3 -c "import yaml,sys; p=yaml.safe_load(sys.stdin); [print(a['name'], len(a['items']), 'items') for a in p['artists']]"

# Download only
python3 scripts/download.py "Paul Thangiah"

# Split jukeboxes
python3 scripts/split_chapters.py "Paul Thangiah"

# Cleanup
python3 scripts/cleanup.py
```

### Step 4: Verify success
```bash
# Check output directory
ls /media/disks/nas/music/

# Count downloaded files for an artist
find /media/disks/nas/music/Paul_Thangiah -name "*.mp3" | wc -l

# Check logs for errors
tail -50 logs/download_*.log | grep -E "✗|ERROR|FAILED"
```

## Error Handling

| Error | Fix |
|-------|-----|
| `Sign in to confirm` or 403 | Cookies expired → refresh `/home/pramod/yt_cookies.txt` |
| `No such file: download_plan.yaml` | Run `research.py` first |
| `No artist matching X` | Check spelling in `artists.yaml` |
| Chapter split produces 0 tracks | Video may not have chapters — skip |
| Download timeout | Re-run `download.py` — `--no-overwrites` skips already done |

## Refreshing Cookies

If downloads fail with authentication errors:
```bash
# Option 1: Manual export from browser using cookies.txt extension
# → Export to /home/pramod/yt_cookies.txt

# Option 2: yt-dlp browser extraction
yt-dlp --cookies-from-browser firefox --skip-download "https://www.youtube.com"
```

## Adding Artists

Edit `/home/pramod/music_pipeline/artists.yaml`:
```yaml
  - name: "New Artist Name"
    aliases: ["Alt Name"]
    known_albums: ["Album 1", "Album 2"]
    fetch_singles: true
    fetch_unknown_albums: true
```

Then: `./pipeline.sh "New Artist Name"`

## Success Criteria

- `download_plan.yaml` exists and has entries for each artist
- `/media/disks/nas/music/<Artist>/` directories exist with MP3 files
- No `✗` errors in the latest download log (or very few — some may be unavailable videos)
- Jukebox folders contain a `tracks/` subdirectory with individual MP3 files
