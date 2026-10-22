"""Shared artist research service (YouTube search -> candidate items).

Used by scripts/research.py, the HTTP API and the desktop app. No web/UI dependencies.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.queue_manager import (
    ROOT_DIR,
    _SUBPROCESS_FLAGS,
    _js_runtime_args,
    _subprocess_env,
    _ytdlp_cmd,
)

LogFn = Callable[[str], None]
SEARCH_DELAY = 2


class ResearchCancelled(Exception):
    pass


def classify_item(item: dict) -> str:
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
    return "single"


def safe_name(value: str) -> str:
    value = re.sub(r'[｜：|:/\\?*"<>]', "", value)
    return re.sub(r"\s+", " ", value).strip()


def _to_int(value: str) -> int:
    try:
        return int(float(value)) if value and value != "NA" else 0
    except ValueError:
        return 0


def run_ytdlp_flat(url: str, cookies_path: Optional[str], log: LogFn) -> List[dict]:
    cmd = [
        *_ytdlp_cmd(),
        "--flat-playlist",
        "--no-warnings",
        "--print",
        "%(id)s\t%(title)s\t%(duration)s\t%(n_entries)s\t%(webpage_url)s",
        *_js_runtime_args(),
    ]
    if cookies_path and Path(cookies_path).exists():
        cmd += ["--cookies", cookies_path]
    cmd.append(url)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, creationflags=_SUBPROCESS_FLAGS, env=_subprocess_env()
        )
    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT: {url}")
        return []
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp was not found. Install it (pip install yt-dlp) and try again.") from exc
    except Exception as exc:
        log(f"  ERROR: {exc}")
        return []

    results = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        vid_id = parts[0].strip()
        results.append(
            {
                "id": vid_id,
                "title": parts[1].strip(),
                "duration": _to_int(parts[2].strip()) if len(parts) > 2 else 0,
                "n_entries": _to_int(parts[3].strip()) if len(parts) > 3 else 0,
                "url": (parts[4].strip() if len(parts) > 4 else "") or f"https://www.youtube.com/watch?v={vid_id}",
            }
        )
    return results


def research_artist(
    artist_cfg: dict,
    cookies_path: Optional[str] = None,
    log: LogFn = print,
    cancel: Optional[threading.Event] = None,
    on_item: Optional[Callable[[dict], None]] = None,
    save_log: bool = True,
) -> dict:
    cancel = cancel or threading.Event()
    name = artist_cfg["name"]
    aliases = artist_cfg.get("aliases", [])
    known_albums = artist_cfg.get("known_albums", [])
    fetch_singles = artist_cfg.get("fetch_singles", True)
    fetch_unknown = artist_cfg.get("fetch_unknown_albums", True)
    name_parts = [part for part in name.lower().split() if len(part) > 3]
    search_names = [name] + aliases[:1]

    def pause() -> None:
        if cancel.wait(SEARCH_DELAY):
            raise ResearchCancelled()

    def check() -> None:
        if cancel.is_set():
            raise ResearchCancelled()

    found: Dict[str, dict] = {}

    def add(entry: dict, item_type: str, **extra: object) -> None:
        item = {
            "id": entry["id"],
            "title": entry["title"],
            "url": entry["url"],
            "type": item_type,
            "duration": entry["duration"],
            **extra,
        }
        found[entry["id"]] = item
        log(f"    Found ({item_type}): {entry['title'][:70]}")
        if on_item:
            on_item(item)

    def name_matches(entry: dict) -> bool:
        title = entry["title"].lower()
        return any(part in title for part in name_parts)

    log(f"Researching: {name}")

    for album in known_albums:
        log(f"  Searching known album: {album}")
        album_words = [w for w in album.lower().split() if len(w) > 2]
        for search_name in search_names:
            check()
            for entry in run_ytdlp_flat(f'ytsearch10:"{search_name}" "{album}" Tamil Christian', cookies_path, log):
                title = entry["title"].lower()
                matches = sum(1 for w in album_words if w in title)
                if matches >= max(1, len(album_words) // 2) and entry["id"] not in found:
                    add(entry, classify_item(entry), album_hint=album)
            pause()

    if fetch_unknown:
        for search_name in search_names:
            log(f"  General album search for: {search_name}")
            for query in (
                f'"{search_name}" Tamil Christian full album',
                f'"{search_name}" Tamil Christian songs playlist',
            ):
                check()
                for entry in run_ytdlp_flat(f"ytsearch15:{query}", cookies_path, log):
                    if entry["id"] not in found and name_matches(entry):
                        add(entry, classify_item(entry))
                pause()

    if fetch_singles:
        log("  Searching singles...")
        for search_name in search_names:
            check()
            for entry in run_ytdlp_flat(f'ytsearch20:"{search_name}" Tamil Christian song', cookies_path, log):
                if entry["id"] not in found and 60 < entry["duration"] < 900 and name_matches(entry):
                    add(entry, "single")
            pause()

    items = list(found.values())
    log(
        f"  Total found for {name}: {len(items)} items "
        f"({sum(i['type'] in ('album_playlist', 'artist_playlist') for i in items)} playlists, "
        f"{sum(i['type'] == 'jukebox' for i in items)} jukeboxes, "
        f"{sum(i['type'] == 'single' for i in items)} singles)"
    )

    if save_log:
        logs_dir = ROOT_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / f"research_{re.sub(r'[^\w]', '_', name)}_{stamp}.json"
        log_file.write_text(json.dumps({"artist": name, "items": items}, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"  Saved research log: {log_file}")

    return {"name": name, "folder_name": safe_name(name).replace(" ", "_"), "items": items}


class ResearchManager:
    """Runs one research job at a time in a background thread so UIs can poll it."""

    def __init__(self, cookies_path_provider: Callable[[], str]) -> None:
        self._cookies = cookies_path_provider
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.status = "idle"  # idle | running | done | failed | cancelled
        self.artist = ""
        self.folder_name = ""
        self.log: List[str] = []
        self.items: List[dict] = []
        self.error = ""

    def start(self, artist_cfg: dict) -> None:
        name = (artist_cfg.get("name") or "").strip()
        if not name:
            raise ValueError("Artist name is required")
        with self._lock:
            if self.status == "running":
                raise RuntimeError("A research job is already running")
            self._cancel = threading.Event()
            self.status = "running"
            self.artist = name
            self.folder_name = safe_name(name).replace(" ", "_")
            self.log = []
            self.items = []
            self.error = ""
            cfg = {**artist_cfg, "name": name}
            self._thread = threading.Thread(target=self._run, args=(cfg, self._cancel), daemon=True)
            self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self, cfg: dict, cancel: threading.Event) -> None:
        try:
            research_artist(
                cfg,
                cookies_path=self._cookies(),
                log=self.log.append,
                cancel=cancel,
                on_item=self.items.append,
            )
            self.status = "done"
        except ResearchCancelled:
            self.log.append("Research cancelled.")
            self.status = "cancelled"
        except Exception as exc:
            self.error = str(exc)
            self.log.append(f"ERROR: {exc}")
            self.status = "failed"

    def snapshot(self) -> dict:
        return {
            "status": self.status,
            "artist": self.artist,
            "folder_name": self.folder_name,
            "error": self.error,
            "log": list(self.log[-300:]),
            "items": list(self.items),
        }
