#!/usr/bin/env python3
"""
research.py — Research Tamil Christian artists on YouTube/YT Music
Outputs download_plan.yaml with all found content organized by artist/album.

Usage:
  python3 research.py               # research all artists
  python3 research.py "Paul Thangiah"   # research specific artist
"""

import subprocess, json, os, re, sys, time, datetime
from pathlib import Path
import yaml

SCRIPT_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPT_DIR.parent

def load_config():
    config_path = PIPELINE_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}

CONFIG = load_config()

COOKIES = str(PIPELINE_DIR / CONFIG.get("paths", {}).get("cookies", "cookies.txt"))
LOGS_DIR = PIPELINE_DIR / CONFIG.get("paths", {}).get("logs", "logs")
PLAN_FILE = PIPELINE_DIR / "download_plan.yaml"
DENO_BIN = CONFIG.get("paths", {}).get("deno", "/home/pramod/.deno/bin")
err_cfg = CONFIG.get("error_handling", {})

LOGS_DIR.mkdir(exist_ok=True)

env = os.environ.copy()
LOCAL_BIN = os.path.expanduser("~/.local/bin")
env["PATH"] = LOCAL_BIN + ":" + env.get("PATH", "") + f":{DENO_BIN}"

def log(msg):
    print(msg, flush=True)

def validate_cookies(cookies_path):
    if not os.path.exists(cookies_path):
        raise FileNotFoundError(
            f"cookies.txt not found at {cookies_path}. Export from your browser."
        )
    age_days = (time.time() - os.path.getmtime(cookies_path)) / 86400
    if age_days > 7:
        log(f"⚠ cookies.txt is {age_days:.0f} days old — may need refresh")
    log("Validating cookies...")
    try:
        result = subprocess.run(
            ['yt-dlp', '--cookies', cookies_path, '--skip-download',
             '--print', 'title', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'],
            capture_output=True, text=True, timeout=30, env=env
        )
        if 'Sign in' in result.stderr or 'bot' in result.stderr.lower():
            if err_cfg.get("fail_on_cookie_error", True):
                raise RuntimeError("Cookie validation failed — cookies expired. Please refresh.")
            else:
                log("⚠ Cookie validation failed but continuing (fail_on_cookie_error=false)")
        else:
            log("✓ Cookies valid")
    except subprocess.TimeoutExpired:
        log("⚠ Cookie validation timed out — continuing anyway")
    return True

def run_ytdlp_flat(url, extra_args=None):
    cmd = [
        "yt-dlp", "--flat-playlist", "--no-warnings",
        "--print", "%(id)s\t%(title)s\t%(duration)s\t%(n_entries)s\t%(webpage_url)s",
        "--cookies", COOKIES,
    ]
    if extra_args:
        cmd += extra_args
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        results = []
        for line in r.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                vid_id = parts[0].strip()
                title = parts[1].strip() if len(parts) > 1 else ""
                duration = parts[2].strip() if len(parts) > 2 else ""
                n_entries = parts[3].strip() if len(parts) > 3 else ""
                url_out = parts[4].strip() if len(parts) > 4 else ""
                try:
                    dur = int(float(duration)) if duration and duration != "NA" else 0
                except:
                    dur = 0
                try:
                    entries = int(n_entries) if n_entries and n_entries != "NA" else 0
                except:
                    entries = 0
                results.append({
                    "id": vid_id,
                    "title": title,
                    "duration": dur,
                    "n_entries": entries,
                    "url": url_out or f"https://www.youtube.com/watch?v={vid_id}",
                })
        return results
    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT: {url}")
        return []
    except Exception as e:
        log(f"  ERROR: {e}")
        return []

def search_youtube(query, limit=15):
    return run_ytdlp_flat(f"ytsearch{limit}:{query}")

def classify_item(item, artist_name):
    title = item.get("title", "").lower()
    dur = item.get("duration", 0)
    entries = item.get("n_entries", 0)

    if entries > 5:
        if any(kw in title for kw in ["vol ", "volume", "album", "collection"]):
            return "album_playlist"
        return "artist_playlist"
    if entries > 1:
        return "album_playlist"
    if dur > 1500:
        return "jukebox"
    if dur > 60:
        return "single"
    return "single"

def safe_name(s):
    s = re.sub(r'[｜：|:/\\?*"<>]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def research_artist(artist_cfg, output_base):
    name = artist_cfg["name"]
    aliases = artist_cfg.get("aliases", [])
    known_albums = artist_cfg.get("known_albums", [])
    fetch_singles = artist_cfg.get("fetch_singles", True)
    fetch_unknown = artist_cfg.get("fetch_unknown_albums", True)

    log(f"\n{'='*60}")
    log(f"Researching: {name}")
    log(f"{'='*60}")

    found = {}

    # 1. Known albums
    for album in known_albums:
        log(f"  Searching known album: {album}")
        for search_name in [name] + aliases[:1]:
            results = search_youtube(f'"{search_name}" "{album}" Tamil Christian', limit=10)
            for r in results:
                title_low = r["title"].lower()
                album_low = album.lower()
                album_words = [w for w in album_low.split() if len(w) > 2]
                matches = sum(1 for w in album_words if w in title_low)
                if matches >= max(1, len(album_words) // 2):
                    vid_id = r["id"]
                    if vid_id not in found:
                        item_type = classify_item(r, name)
                        found[vid_id] = {
                            "id": vid_id, "title": r["title"], "url": r["url"],
                            "type": item_type, "album_hint": album, "duration": r["duration"],
                        }
                        log(f"    Found ({item_type}): {r['title'][:70]}")
            time.sleep(2)

    # 2. General search
    if fetch_unknown:
        for search_name in [name] + aliases[:1]:
            log(f"  General album search for: {search_name}")
            for q in [
                f'"{search_name}" Tamil Christian full album',
                f'"{search_name}" Tamil Christian songs playlist',
            ]:
                results = search_youtube(q, limit=15)
                for r in results:
                    vid_id = r["id"]
                    if vid_id not in found:
                        item_type = classify_item(r, name)
                        title_low = r["title"].lower()
                        name_parts = name.lower().split()
                        if any(part in title_low for part in name_parts if len(part) > 3):
                            found[vid_id] = {
                                "id": vid_id, "title": r["title"], "url": r["url"],
                                "type": item_type, "duration": r["duration"],
                            }
                            log(f"    Found ({item_type}): {r['title'][:70]}")
                time.sleep(2)

    # 3. Singles
    if fetch_singles:
        log(f"  Searching singles...")
        for search_name in [name] + aliases[:1]:
            results = search_youtube(f'"{search_name}" Tamil Christian song', limit=20)
            for r in results:
                vid_id = r["id"]
                dur = r.get("duration", 0)
                if vid_id not in found and 60 < dur < 900:
                    title_low = r["title"].lower()
                    name_parts = name.lower().split()
                    if any(part in title_low for part in name_parts if len(part) > 3):
                        found[vid_id] = {
                            "id": vid_id, "title": r["title"], "url": r["url"],
                            "type": "single", "duration": dur,
                        }
                        log(f"    Found (single): {r['title'][:70]}")
            time.sleep(2)

    items_list = list(found.values())
    log(f"\n  Total found for {name}: {len(items_list)} items")
    log(f"  Breakdown: {sum(1 for i in items_list if i['type']=='album_playlist')} album_playlists, "
        f"{sum(1 for i in items_list if i['type']=='jukebox')} jukeboxes, "
        f"{sum(1 for i in items_list if i['type']=='single')} singles")

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_artist = re.sub(r'[^\w]', '_', name)
    log_file = LOGS_DIR / f"research_{safe_artist}_{ts}.json"
    with open(log_file, "w") as f:
        json.dump({"artist": name, "items": items_list}, f, indent=2, ensure_ascii=False)
    log(f"  Saved research log: {log_file}")

    return {
        "name": name,
        "output_dir": os.path.join(output_base, safe_name(name).replace(" ", "_")),
        "items": items_list,
    }

def main():
    validate_cookies(COOKIES)

    config_file = PIPELINE_DIR / "artists.yaml"
    with open(config_file) as f:
        config = yaml.safe_load(f)

    output_base = config.get("output_base", CONFIG.get("paths", {}).get("output_base", "/media/disks/nas/music"))
    artists = config.get("artists", [])

    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target != "all":
        artists = [a for a in artists if target.lower() in a["name"].lower()]
        if not artists:
            print(f"No artist matching '{target}' found in artists.yaml")
            sys.exit(1)

    existing_plan = {}
    if PLAN_FILE.exists():
        with open(PLAN_FILE) as f:
            existing = yaml.safe_load(f) or {}
            for a in existing.get("artists", []):
                existing_plan[a["name"]] = a

    plan_artists = []
    for artist_cfg in artists:
        result = research_artist(artist_cfg, output_base)
        if artist_cfg["name"] in existing_plan:
            existing_ids = {i["id"] for i in existing_plan[artist_cfg["name"]].get("items", [])}
            new_items = [i for i in result["items"] if i["id"] not in existing_ids]
            result["items"] = existing_plan[artist_cfg["name"]]["items"] + new_items
        plan_artists.append(result)
        time.sleep(5)

    plan = {"output_base": output_base, "artists": plan_artists}
    with open(PLAN_FILE, "w") as f:
        yaml.dump(plan, f, allow_unicode=True, default_flow_style=False)
    print(f"\nDownload plan saved: {PLAN_FILE}")
    total = sum(len(a["items"]) for a in plan_artists)
    print(f"Total items in plan: {total}")

if __name__ == "__main__":
    main()
