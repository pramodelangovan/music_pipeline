#!/usr/bin/env python3
"""
download.py — Download Tamil Christian music from download_plan.yaml

Usage:
  python3 download.py               # download all artists
  python3 download.py "Paul Thangiah"   # download specific artist
  python3 download.py all --no-tui      # disable TUI
"""

import subprocess, os, re, sys, time, datetime, logging, json
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

# Paths
COOKIES = str(PIPELINE_DIR / CONFIG.get("paths", {}).get("cookies", "cookies.txt"))
LOGS_DIR = PIPELINE_DIR / CONFIG.get("paths", {}).get("logs", "logs")
PLAN_FILE = PIPELINE_DIR / "download_plan.yaml"
DENO_BIN = CONFIG.get("paths", {}).get("deno", "/home/pramod/.deno/bin")

LOGS_DIR.mkdir(exist_ok=True)

env = os.environ.copy()
LOCAL_BIN = os.path.expanduser("~/.local/bin")
env["PATH"] = LOCAL_BIN + ":" + env.get("PATH", "") + f":{DENO_BIN}"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = LOGS_DIR / f"download_{ts}.log"

# Config sections
ytdlp_cfg = CONFIG.get("yt_dlp", {})
err_cfg = CONFIG.get("error_handling", {})
notif_cfg = CONFIG.get("notifications", {})
delays_cfg = CONFIG.get("delays", {})

log_level = getattr(logging, notif_cfg.get("log_level", "INFO").upper(), logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger()

# Determine TUI mode
USE_TUI = notif_cfg.get("show_tui", True) and "--no-tui" not in sys.argv
if USE_TUI:
    try:
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
        from rich.table import Table
        from rich.live import Live
        from rich.panel import Panel
        from rich.text import Text
        console = Console()
    except ImportError:
        USE_TUI = False
        log.warning("rich not installed, TUI disabled. Install with: pip3 install rich")

# ── Error types ──────────────────────────────────────────────────────────────

ERROR_TYPES = {
    'bot_detected': ['Sign in to confirm', 'not a bot', 'Confirm you'],
    'unavailable': ['Video unavailable', 'has been terminated', 'private video',
                    'This video is not available', 'removed by the uploader'],
    'copyright': ['blocked it', 'copyright'],
    'network': ['Connection refused', 'timed out', 'Network error', 'unable to connect'],
}

class BotDetectionError(Exception):
    pass

def classify_error(stderr):
    for error_type, patterns in ERROR_TYPES.items():
        if any(p.lower() in stderr.lower() for p in patterns):
            return error_type
    return 'unknown'

# ── Cookie validation ─────────────────────────────────────────────────────────

def validate_cookies(cookies_path):
    if not os.path.exists(cookies_path):
        raise FileNotFoundError(
            f"cookies.txt not found at {cookies_path}. Export from your browser."
        )
    age_days = (time.time() - os.path.getmtime(cookies_path)) / 86400
    if age_days > 7:
        log.warning(f"⚠ cookies.txt is {age_days:.0f} days old — may need refresh")
    log.info("Validating cookies...")
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
                log.warning("Cookie validation failed but continuing (fail_on_cookie_error=false)")
        else:
            log.info("✓ Cookies valid")
    except subprocess.TimeoutExpired:
        log.warning("Cookie validation timed out — continuing anyway")
    return True

# ── yt-dlp base command ───────────────────────────────────────────────────────

def build_ytdlp_base():
    return [
        "yt-dlp", "-x",
        "--audio-format", ytdlp_cfg.get("audio_format", "mp3"),
        "--audio-quality", str(ytdlp_cfg.get("audio_quality", 0)),
        "--embed-thumbnail", "--add-metadata",
        "--no-overwrites",
        "--retries", str(ytdlp_cfg.get("retries", 5)),
        "--sleep-interval", str(ytdlp_cfg.get("sleep_interval", 3)),
        "--max-sleep-interval", str(ytdlp_cfg.get("max_sleep_interval", 8)),
        "--cookies", COOKIES,
        "--remote-components", ytdlp_cfg.get("remote_components", "ejs:github"),
    ]

YTDLP_BASE = build_ytdlp_base()

# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_name(s):
    s = re.sub(r'[｜：|:/\\?*"<>]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

# ── Download with retry ───────────────────────────────────────────────────────

def run_ytdlp(cmd):
    try:
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        class _R:
            returncode = -1
            stderr = "TIMEOUT"
            stdout = ""
        return _R()
    except Exception as e:
        class _R:
            returncode = -1
            stderr = str(e)
            stdout = ""
        return _R()

def download_with_retry(cmd, url, max_retries=None):
    if max_retries is None:
        max_retries = ytdlp_cfg.get("retries", 3)
    errors = []
    for attempt in range(max(1, max_retries)):
        result = run_ytdlp(cmd)
        if result.returncode == 0:
            return True, []

        error_type = classify_error(result.stderr + result.stdout)
        err_msg = (result.stderr or result.stdout)[-400:]
        errors.append({"url": url, "type": error_type, "message": err_msg, "attempt": attempt + 1})

        if error_type == 'bot_detected':
            if err_cfg.get("retry_on_bot_detection", True):
                wait = err_cfg.get("retry_delay", 300)
                log.warning(f"  🤖 Bot detected, waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise BotDetectionError("Bot detected — cookies may be expired")

        elif error_type in ('unavailable', 'copyright'):
            if err_cfg.get("skip_unavailable", True):
                log.warning(f"  ⏭ Skipping ({error_type}): {url}")
                return False, errors  # don't retry

        else:
            wait = 2 ** attempt * 10
            log.warning(f"  ↺ Error ({error_type}, attempt {attempt+1}/{max_retries}), retrying in {wait}s...")
            time.sleep(wait)

    return False, errors

# ── Item download ─────────────────────────────────────────────────────────────

def download_item(item, artist_dir):
    item_type = item.get("type", "single")
    url = item["url"]
    title = item.get("title", "unknown")
    album_hint = item.get("album_hint", "")

    log.info(f"  [{item_type}] {title[:70]}")

    if item_type == "album_playlist":
        album_name = safe_name(album_hint or title).replace(" ", "_")
        out_dir = os.path.join(artist_dir, album_name[:60])
        os.makedirs(out_dir, exist_ok=True)
        cmd = YTDLP_BASE + [
            "-o", os.path.join(out_dir, "%(playlist_index)02d - %(title)s.%(ext)s"), url
        ]
    elif item_type == "artist_playlist":
        out_dir = os.path.join(artist_dir, "All_Songs")
        os.makedirs(out_dir, exist_ok=True)
        cmd = YTDLP_BASE + [
            "-o", os.path.join(out_dir, "%(playlist_index)02d - %(title)s.%(ext)s"), url
        ]
    elif item_type == "jukebox":
        album_name = safe_name(album_hint or title).replace(" ", "_")
        out_dir = os.path.join(artist_dir, album_name[:60])
        os.makedirs(out_dir, exist_ok=True)
        cmd = YTDLP_BASE + ["-o", os.path.join(out_dir, "%(title)s.%(ext)s"), url]
    else:  # single
        out_dir = os.path.join(artist_dir, "Singles")
        os.makedirs(out_dir, exist_ok=True)
        cmd = YTDLP_BASE + ["-o", os.path.join(out_dir, "%(title)s.%(ext)s"), url]

    success, errors = download_with_retry(cmd, url)
    if success:
        log.info("    ✓ Done")
    return success, errors

# ── Artist download ───────────────────────────────────────────────────────────

def download_artist(artist_plan, progress=None, artist_task=None):
    name = artist_plan["name"]
    artist_dir = artist_plan["output_dir"]
    items = artist_plan.get("items", [])

    log.info(f"\n{'='*60}")
    log.info(f"Downloading: {name} → {artist_dir}")
    log.info(f"Total items: {len(items)}")
    log.info(f"{'='*60}")

    os.makedirs(artist_dir, exist_ok=True)

    album_types = {"album_playlist", "artist_playlist", "jukebox"}
    albums = [i for i in items if i["type"] in album_types]
    singles = [i for i in items if i["type"] == "single"]

    ok = 0
    fail = 0
    all_errors = []
    error_count = 0
    max_errors = err_cfg.get("max_errors_per_artist", 10)

    def do_item(item, delay):
        nonlocal ok, fail, error_count
        if error_count >= max_errors:
            log.warning(f"  ⛔ Max errors ({max_errors}) reached for {name}, stopping artist")
            return False  # signal stop
        success, errs = download_item(item, artist_dir)
        all_errors.extend(errs)
        if success:
            ok += 1
        else:
            fail += 1
            error_count += len(errs)
        if progress and artist_task is not None:
            progress.update(artist_task,
                description=f"[green]{item.get('title','')[:40]}",
                advance=1)
        time.sleep(delay)
        return True  # continue

    delay_album = delays_cfg.get("between_albums", 40)
    delay_single = delays_cfg.get("between_singles", 10)

    for item in albums:
        if not do_item(item, delay_album):
            break
    for item in singles:
        if not do_item(item, delay_single):
            break

    log.info(f"\n  {name}: {ok} ok, {fail} failed")

    # Save error report
    if notif_cfg.get("save_error_report", True) and all_errors:
        report = {
            "artist": name,
            "timestamp": datetime.datetime.now().isoformat(),
            "success": ok,
            "failed": fail,
            "skipped": sum(1 for e in all_errors if e["type"] in ("unavailable", "copyright")),
            "errors": all_errors,
        }
        report_file = LOGS_DIR / f"errors_{name.replace(' ','_')}_{ts}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        log.info(f"  Error report: {report_file}")

    return ok, fail

# ── TUI helpers ───────────────────────────────────────────────────────────────

def make_status_table(artists_status):
    table = Table(title="🎵 Tamil Christian Music Downloader", show_header=True, header_style="bold magenta")
    table.add_column("Artist", style="cyan", width=25)
    table.add_column("Status", width=12)
    table.add_column("Downloaded", justify="right", width=11)
    table.add_column("Errors", justify="right", width=7)
    table.add_column("Current Track", width=35)
    for artist, s in artists_status.items():
        state = s['state']
        style = {"pending": "dim", "downloading": "yellow", "done": "green", "error": "red"}.get(state, "")
        table.add_row(
            artist,
            Text(state, style=style),
            str(s['downloaded']),
            str(s['errors']),
            (s['current_track'] or "")[:34],
        )
    return table

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    validate_cookies(COOKIES)

    if not PLAN_FILE.exists():
        print(f"No download_plan.yaml found at {PLAN_FILE}")
        print("Run research.py first.")
        sys.exit(1)

    with open(PLAN_FILE) as f:
        plan = yaml.safe_load(f)

    artists = plan.get("artists", [])
    # Strip --no-tui from argv before checking artist arg
    args = [a for a in sys.argv[1:] if a != "--no-tui"]
    target = args[0] if args else "all"

    if target != "all":
        artists = [a for a in artists if target.lower() in a["name"].lower()]
        if not artists:
            print(f"No artist matching '{target}' in download_plan.yaml")
            sys.exit(1)

    total_ok = 0
    total_fail = 0

    if USE_TUI:
        artists_status = {a["name"]: {"state": "pending", "downloaded": 0, "errors": 0, "current_track": None}
                          for a in artists}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        ) as progress:
            for artist in artists:
                name = artist["name"]
                items = artist.get("items", [])
                artists_status[name]["state"] = "downloading"

                artist_task = progress.add_task(f"[cyan]{name}", total=len(items))

                ok, fail = download_artist(artist, progress=progress, artist_task=artist_task)
                total_ok += ok
                total_fail += fail

                artists_status[name]["state"] = "done" if fail == 0 else "error"
                artists_status[name]["downloaded"] = ok
                artists_status[name]["errors"] = fail

                time.sleep(delays_cfg.get("between_artists", 60))

        console.print(make_status_table(artists_status))
        console.print(Panel(f"[bold green]✓ Download complete:[/] {total_ok} ok, {total_fail} failed\nLog: {log_file}"))

    else:
        for artist in artists:
            ok, fail = download_artist(artist)
            total_ok += ok
            total_fail += fail
            time.sleep(delays_cfg.get("between_artists", 60))

        log.info(f"\n{'='*60}")
        log.info(f"Download complete: {total_ok} ok, {total_fail} failed")
        log.info(f"Log saved: {log_file}")

if __name__ == "__main__":
    main()
