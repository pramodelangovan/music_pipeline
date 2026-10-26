"""Shared artist research service (YouTube search -> candidate items).

Used by the HTTP API and the desktop app. No web/UI dependencies.
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.queue_manager import (
    DB_PATH,
    LOGS_DIR,
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
    seed_items: Optional[List[dict]] = None,
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

    found: Dict[str, dict] = {item["id"]: item for item in (seed_items or [])}

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
        logs_dir = LOGS_DIR
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / f"research_{re.sub(r'[^\w]', '_', name)}_{stamp}.json"
        log_file.write_text(json.dumps({"artist": name, "items": items}, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"  Saved research log: {log_file}")

    return {"name": name, "folder_name": safe_name(name).replace(" ", "_"), "items": items}


class ResearchManager:
    """Runs one research job at a time in a background thread so UIs can poll it.

    State is persisted to SQLite so a research job interrupted by a crash or shutdown
    can be resumed (``resume_interrupted``) on the next launch.
    """

    def __init__(self, cookies_path_provider: Callable[[], str], db_path: Optional[Path] = None) -> None:
        self._cookies = cookies_path_provider
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._shutdown = False
        self._thread: Optional[threading.Thread] = None
        self.status = "idle"  # idle | running | done | failed | cancelled | interrupted
        self.artist = ""
        self.folder_name = ""
        self.log: List[str] = []
        self.items: List[dict] = []
        self.error = ""
        self.cfg: dict = {}

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path or DB_PATH, check_same_thread=False)
        self._db_lock = threading.Lock()
        self._db_closed = False
        with self._db_lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS research_state (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL)"
            )
            self._db.commit()
        self._load()

    def _load(self) -> None:
        with self._db_lock:
            row = self._db.execute("SELECT data FROM research_state WHERE id = 1").fetchone()
        if not row:
            return
        try:
            data = json.loads(row[0])
        except ValueError:
            return
        self.status = data.get("status", "idle")
        self.artist = data.get("artist", "")
        self.folder_name = data.get("folder_name", "")
        self.log = list(data.get("log", []))
        self.items = list(data.get("items", []))
        self.error = data.get("error", "")
        self.cfg = data.get("cfg", {})
        # A job still marked running was killed mid-way (crash, kill, forced close).
        if self.status == "running":
            self.status = "interrupted"
            self._persist()

    def _persist(self) -> None:
        if self._db_closed:
            return
        data = json.dumps(
            {
                "status": self.status,
                "artist": self.artist,
                "folder_name": self.folder_name,
                "log": self.log[-300:],
                "items": self.items,
                "error": self.error,
                "cfg": self.cfg,
            },
            ensure_ascii=False,
        )
        try:
            with self._db_lock:
                self._db.execute("INSERT OR REPLACE INTO research_state (id, data) VALUES (1, ?)", (data,))
                self._db.commit()
        except sqlite3.Error:
            pass

    @property
    def resumable(self) -> bool:
        return self.status == "interrupted" and bool(self.cfg.get("name"))

    def is_active(self) -> bool:
        return self.status == "running"

    def start(self, artist_cfg: dict) -> None:
        name = (artist_cfg.get("name") or "").strip()
        if not name:
            raise ValueError("Artist name is required")
        self._launch({**artist_cfg, "name": name}, fresh=True)

    def resume_interrupted(self) -> bool:
        """Restart an interrupted job, keeping the items already found. Returns True if resumed."""
        if not self.resumable:
            return False
        self._launch(dict(self.cfg), fresh=False)
        return True

    def _launch(self, cfg: dict, fresh: bool) -> None:
        with self._lock:
            if self.status == "running":
                raise RuntimeError("A research job is already running")
            self._cancel = threading.Event()
            self._shutdown = False
            self.status = "running"
            self.artist = cfg["name"]
            self.folder_name = safe_name(cfg["name"]).replace(" ", "_")
            self.cfg = cfg
            self.error = ""
            if fresh:
                self.log = []
                self.items = []
            else:
                self.log.append("Resuming interrupted research...")
            seed = list(self.items)
            self._persist()
            self._thread = threading.Thread(target=self._run, args=(cfg, self._cancel, seed), daemon=True)
            self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def interrupt(self) -> None:
        """Stop for app shutdown while keeping the job resumable on next launch."""
        self._shutdown = True
        self._cancel.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        if self.status == "running":
            self.status = "interrupted"
            self._persist()
        self._db_closed = True

    def _log(self, line: str) -> None:
        self.log.append(line)
        self._persist()

    def _add_item(self, item: dict) -> None:
        self.items.append(item)
        self._persist()

    def _run(self, cfg: dict, cancel: threading.Event, seed: List[dict]) -> None:
        try:
            research_artist(
                cfg,
                cookies_path=self._cookies(),
                log=self._log,
                cancel=cancel,
                on_item=self._add_item,
                seed_items=seed,
            )
            self.status = "done"
        except ResearchCancelled:
            if self._shutdown:
                self.status = "interrupted"
            else:
                self.log.append("Research cancelled.")
                self.status = "cancelled"
        except Exception as exc:
            self.error = str(exc)
            self.log.append(f"ERROR: {exc}")
            self.status = "failed"
        self._persist()

    def snapshot(self) -> dict:
        return {
            "status": self.status,
            "artist": self.artist,
            "folder_name": self.folder_name,
            "error": self.error,
            "resumable": self.resumable,
            "log": list(self.log[-300:]),
            "items": list(self.items),
        }


