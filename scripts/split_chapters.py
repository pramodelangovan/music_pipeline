#!/usr/bin/env python3
"""
split_chapters.py — Split jukebox MP3s into individual tracks using YouTube chapter data.

This is an adapted version of ~/music_scripts/split_chapters.py that:
- Accepts a directory argument (defaults to output_base from artists.yaml)
- Scans the entire directory tree for MP3s that need splitting
- Uses download_plan.yaml to find jukebox video IDs

Usage:
  python3 split_chapters.py                        # process all jukeboxes in output_base
  python3 split_chapters.py /path/to/music/dir     # process specific dir
  python3 split_chapters.py "Paul Thangiah"        # process specific artist
"""

import subprocess, json, os, re, sys, yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(SCRIPT_DIR)
COOKIES = "/home/pramod/yt_cookies.txt"
LOG = "/tmp/chapter_split.log"
PLAN_FILE = os.path.join(PIPELINE_DIR, "download_plan.yaml")

env = os.environ.copy()
env["PATH"] = env.get("PATH", "") + ":/home/pramod/.deno/bin"

def log(msg):
    print(msg, flush=True)
    with open(LOG, "a") as f:
        f.write(msg + "\n")

def get_video_id_from_mp3(mp3_path):
    """Try to extract YouTube video ID from MP3 metadata."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3
        tags = ID3(mp3_path)
        # Check COMM (comment) tags
        for key in tags.keys():
            if key.startswith("COMM"):
                val = str(tags[key])
                m = re.search(r'[a-zA-Z0-9_-]{11}', val)
                if m:
                    return m.group(0)
    except:
        pass
    return None

def get_chapters(video_id):
    r = subprocess.run([
        "yt-dlp", "--cookies", COOKIES,
        "--remote-components", "ejs:github",
        "--skip-download", "--print-json",
        f"https://www.youtube.com/watch?v={video_id}"
    ], capture_output=True, text=True, env=env, timeout=60)
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
        return data.get("chapters") or []
    except:
        return []

def split_mp3(mp3_file, chapters, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    total = len(chapters)
    done = 0
    for i, ch in enumerate(chapters):
        start = ch["start_time"]
        end = ch.get("end_time")
        title = ch["title"].strip()
        safe = re.sub(r'[^\w\s\-\(\)]', '', title).strip()
        safe = re.sub(r'\s+', ' ', safe)
        out = os.path.join(out_dir, f"{i+1:02d} - {safe}.mp3")
        if os.path.exists(out):
            log(f"    [{i+1}/{total}] Already exists: {safe}")
            done += 1
            continue
        cmd = ["ffmpeg", "-y", "-i", mp3_file, "-ss", str(start)]
        if end:
            cmd += ["-to", str(end)]
        cmd += ["-acodec", "copy", out]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0:
            log(f"    [{i+1}/{total}] ✓ {safe}")
            done += 1
        else:
            log(f"    [{i+1}/{total}] ✗ ERROR: {safe}")
    return done

def build_jukebox_map(music_root):
    """Build a map of MP3 path → video ID from download_plan.yaml."""
    jukebox_map = {}
    if not os.path.exists(PLAN_FILE):
        return jukebox_map
    with open(PLAN_FILE) as f:
        plan = yaml.safe_load(f) or {}
    for artist in plan.get("artists", []):
        for item in artist.get("items", []):
            if item.get("type") == "jukebox":
                vid = item["id"]
                artist_dir = artist.get("output_dir", "")
                album_hint = item.get("album_hint", item.get("title", ""))
                album_folder = re.sub(r'[^\w\s]', '', album_hint).strip().replace(" ", "_")[:60]
                folder = os.path.join(artist_dir, album_folder)
                jukebox_map[folder] = vid
    return jukebox_map

def find_jukeboxes_in_dir(root_dir):
    """Find MP3 files that look like jukeboxes (large files, no tracks/ subdir with content)."""
    jukeboxes = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        tracks_dir = os.path.join(dirpath, "tracks")
        existing_tracks = 0
        if os.path.isdir(tracks_dir):
            existing_tracks = len([f for f in os.listdir(tracks_dir) if f.endswith(".mp3")])
        if existing_tracks > 2:
            continue  # Already split

        for fname in filenames:
            if not fname.lower().endswith(".mp3"):
                continue
            fpath = os.path.join(dirpath, fname)
            size_mb = os.path.getsize(fpath) / (1024 * 1024)
            if size_mb > 30:  # Jukeboxes are usually > 30MB
                jukeboxes.append((fpath, dirpath))
    return jukeboxes

def process_directory(music_root, artist_filter=None):
    log("=" * 50)
    log(f"Split Chapters: {music_root}")
    log("=" * 50)

    jukebox_map = build_jukebox_map(music_root)
    jukeboxes = find_jukeboxes_in_dir(music_root)

    log(f"Found {len(jukeboxes)} potential jukeboxes")

    for mp3_path, folder in jukeboxes:
        if artist_filter:
            if artist_filter.lower() not in folder.lower():
                continue

        log(f"\nProcessing: {os.path.relpath(mp3_path, music_root)}")
        tracks_dir = os.path.join(folder, "tracks")

        # Find video ID: from plan map or metadata
        vid = jukebox_map.get(folder)
        if not vid:
            vid = get_video_id_from_mp3(mp3_path)
        if not vid:
            log(f"  SKIP: Cannot determine video ID")
            continue

        log(f"  Video ID: {vid}")
        log(f"  Fetching chapters...")
        chapters = get_chapters(vid)

        if len(chapters) < 2:
            log(f"  SKIP: Only {len(chapters)} chapter(s) found")
            continue

        log(f"  Found {len(chapters)} chapters → splitting")
        done = split_mp3(mp3_path, chapters, tracks_dir)
        log(f"  Done: {done}/{len(chapters)} tracks")

    log("\n" + "=" * 50)
    log("All splits complete!")

def main():
    config_file = os.path.join(PIPELINE_DIR, "artists.yaml")
    with open(config_file) as f:
        config = yaml.safe_load(f)
    output_base = config.get("output_base", "/media/disks/nas/music")

    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg and os.path.isdir(arg):
        process_directory(arg)
    elif arg:
        # Treat as artist filter
        process_directory(output_base, artist_filter=arg)
    else:
        process_directory(output_base)

if __name__ == "__main__":
    main()
