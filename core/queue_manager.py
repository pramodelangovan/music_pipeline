"""Shared queue/download service used by both the HTTP API and the desktop app.

This module has no web or UI dependencies, so any front-end can drive it directly.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parents[1]

CONFIG_PATH = ROOT_DIR / "config.yaml"
DEFAULT_OUTPUT_BASE = ROOT_DIR / "downloads"
RUNTIME_SETTINGS_PATH = ROOT_DIR / "logs" / "runtime_settings.json"
DB_PATH = ROOT_DIR / "logs" / "downloads.db"

# Avoid flashing console windows when running yt-dlp from a windowed app.
_SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _js_runtime_args() -> List[str]:
    """yt-dlp flags selecting an available JS runtime (deno preferred, then node)."""
    extra_path = os.pathsep.join([str(Path.home() / ".deno" / "bin"), os.environ.get("PATH", "")])
    for name in ("deno", "node"):
        if shutil.which(name, path=extra_path):
            return ["--js-runtimes", name, "--remote-components", "ejs:github"]
    return []


def _subprocess_env() -> dict:
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(Path.home() / ".deno" / "bin"), env.get("PATH", "")])
    return env


def _ytdlp_cmd() -> List[str]:
    """Command prefix for yt-dlp: the binary on PATH, else this interpreter's yt_dlp module."""
    if shutil.which("yt-dlp", path=_subprocess_env()["PATH"]):
        return ["yt-dlp"]
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "yt_dlp"]
    return ["yt-dlp"]


def _tools_dir() -> Path:
    bundled = Path(getattr(sys, "_MEIPASS", ROOT_DIR)) / "tools"
    return bundled if bundled.exists() else ROOT_DIR / "tools"


def _refresh_path() -> None:
    """Pick up PATH changes made by installers while this process was running."""
    if sys.platform != "win32":
        return
    import winreg

    parts: List[str] = []
    for hive, sub in (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                parts.append(os.path.expandvars(value))
        except OSError:
            continue
    parts.append(os.environ.get("PATH", ""))
    os.environ["PATH"] = os.pathsep.join(p for p in parts if p)


def _missing_dependencies() -> List[str]:
    env_path = _subprocess_env()["PATH"]
    missing = []
    if not shutil.which("ffmpeg", path=env_path):
        missing.append("ffmpeg")
    if not (shutil.which("deno", path=env_path) or shutil.which("node", path=env_path)):
        missing.append("deno")
    return missing


def ensure_dependencies() -> tuple[bool, str]:
    """Run the platform setup script if ffmpeg or a JS runtime is missing."""
    missing = _missing_dependencies()
    if not missing:
        return True, ""

    tools = _tools_dir()
    if sys.platform == "win32":
        shell = shutil.which("powershell") or shutil.which("pwsh")
        cmd = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(tools / "setup.ps1")] if shell else None
    else:
        cmd = ["bash", str(tools / "setup.sh")]
    script_file = tools / ("setup.ps1" if sys.platform == "win32" else "setup.sh")
    if not cmd or not script_file.exists():
        return False, f"Missing {', '.join(missing)} and no setup script was found in {tools}"

    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_SUBPROCESS_FLAGS)
    _refresh_path()
    still_missing = _missing_dependencies()
    if still_missing:
        detail = (result.stderr or result.stdout or "").strip()[-600:]
        return False, f"Setup could not install {', '.join(still_missing)}. {detail}"
    return True, ""


@dataclass
class QueueItem:
    url: str
    media_type: Literal["audio", "video"] = "audio"
    folder_name: str = "youtube_playlist"


@dataclass
class DownloadJob:
    id: str
    source_url: str
    resolved_url: str
    media_type: Literal["audio", "video"]
    folder_name: str
    status: Literal["queued", "downloading", "done", "failed"] = "queued"
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class DownloadManager:
    def __init__(self) -> None:
        # When set (Docker), downloads are confined to this directory (the mounted volume).
        root_env = os.environ.get("MP_DOWNLOAD_ROOT", "").strip()
        self.restricted = bool(root_env)
        self.download_root = Path(root_env).expanduser().resolve() if root_env else None
        self.settings_path = (
            ROOT_DIR / "logs" / "runtime_settings.docker.json" if self.restricted else RUNTIME_SETTINGS_PATH
        )
        cfg = self._load_config()
        queue_cfg = cfg.get("queue_download", {})
        self.cookies_path = str((ROOT_DIR / cfg.get("paths", {}).get("cookies", "cookies.txt")).resolve())
        configured_output = queue_cfg.get("output_base") or DEFAULT_OUTPUT_BASE
        if self.restricted:
            self.output_base = str(self.download_root)
        else:
            self.output_base = self._resolve_path(configured_output)
        self.gap_seconds = int(queue_cfg.get("gap_seconds", 12))
        self._load_runtime_settings()

        self.download_queue: queue.Queue[DownloadJob] = queue.Queue()
        self.inbox_queue: queue.Queue[QueueItem] = queue.Queue()
        self.jobs: Dict[str, DownloadJob] = {}
        self.lock = threading.Lock()
        self.db_lock = threading.Lock()
        self.stop_event = threading.Event()
        self._started = False
        self.run_event = threading.Event()
        self.run_event.set()
        self._deps_checked = False
        self._deps_lock = threading.Lock()
        self.setup_message = ""

        Path(self.output_base).mkdir(parents=True, exist_ok=True)
        (ROOT_DIR / "logs").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init_db()
        # Jobs left over from a previous run wait for an explicit Start Queue.
        if self._recover_jobs():
            self.run_event.clear()

        self.queue_agent = threading.Thread(target=self._queue_agent_loop, daemon=True)
        self.download_agent = threading.Thread(target=self._download_agent_loop, daemon=True)

    def _init_db(self) -> None:
        with self.db_lock:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    resolved_url TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    folder_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    cleared INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self.db.commit()

    def _load_config(self) -> dict:
        if not CONFIG_PATH.exists():
            return {}
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def _load_runtime_settings(self) -> None:
        if not self.settings_path.exists():
            return
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(payload.get("gap_seconds"), int):
                self.gap_seconds = max(0, min(3600, payload["gap_seconds"]))
            if isinstance(payload.get("output_base"), str) and payload["output_base"].strip():
                self.output_base = self._validate_output_base(payload["output_base"])
        except Exception:
            return

    def _save_runtime_settings(self) -> None:
        payload = {
            "gap_seconds": self.gap_seconds,
            "output_base": self.output_base,
            "cookies_path": self.cookies_path,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _resolve_path(self, path_value: str | Path) -> str:
        target = Path(path_value).expanduser()
        if not target.is_absolute():
            target = ROOT_DIR / target
        return str(target.resolve())

    def _validate_output_base(self, path_value: str | Path) -> str:
        """Resolve a download folder; in restricted mode it must live inside the download root."""
        if not self.restricted:
            return self._resolve_path(path_value)
        target = Path(path_value).expanduser()
        if not target.is_absolute():
            target = self.download_root / target
        target = target.resolve()
        if target != self.download_root and self.download_root not in target.parents:
            raise ValueError(f"Download folder must be inside {self.download_root}")
        return str(target)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.queue_agent.start()
        self.download_agent.start()

    def stop(self) -> None:
        self.stop_event.set()
        try:
            self.db.close()
        except Exception:
            pass

    def submit(self, items: List[QueueItem]) -> dict:
        accepted = 0
        for item in items:
            self.inbox_queue.put(item)
            accepted += 1
        return {"accepted": accepted}

    def list_jobs(self) -> List[dict]:
        with self.db_lock:
            rows = self.db.execute(
                """
                SELECT id, source_url, resolved_url, media_type, folder_name, status, error,
                       created_at, started_at, finished_at
                FROM downloads
                WHERE cleared = 0
                ORDER BY created_at DESC
                LIMIT 300
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def pause(self) -> None:
        """Stop starting new downloads; a download already in progress finishes."""
        self.run_event.clear()

    def _recover_jobs(self) -> int:
        """Reload queued/interrupted jobs from the database that are not tracked in memory."""
        with self.db_lock:
            rows = self.db.execute(
                """
                SELECT id, source_url, resolved_url, media_type, folder_name, created_at
                FROM downloads
                WHERE cleared = 0 AND status IN ('queued', 'downloading')
                ORDER BY created_at ASC
                """
            ).fetchall()
        recovered = []
        with self.lock:
            for row in rows:
                if row["id"] in self.jobs:
                    continue
                job = DownloadJob(
                    id=row["id"],
                    source_url=row["source_url"],
                    resolved_url=row["resolved_url"],
                    media_type=row["media_type"],
                    folder_name=row["folder_name"],
                    created_at=row["created_at"],
                )
                self.jobs[job.id] = job
                recovered.append(job)
        for job in recovered:
            self._persist_job(job)
            self.download_queue.put(job)
        return len(recovered)

    def resume(self) -> int:
        """Start the queue, including any queued jobs not yet loaded. Returns jobs recovered."""
        recovered = self._recover_jobs()
        self.run_event.set()
        return recovered

    @property
    def paused(self) -> bool:
        return not self.run_event.is_set()

    def jobs_snapshot(self) -> dict:
        return {
            "paused": self.paused,
            "setup_message": self.setup_message,
            "jobs": self.list_jobs(),
            "pending_queue": self.download_queue.qsize(),
            "pending_inbox": self.inbox_queue.qsize(),
        }

    def list_history(self, limit: int = 1000) -> List[dict]:
        with self.db_lock:
            rows = self.db.execute(
                """
                SELECT id, source_url, resolved_url, media_type, folder_name, status, error,
                       created_at, started_at, finished_at, cleared
                FROM downloads
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_recent(self) -> int:
        with self.lock:
            finished_ids = [
                job_id
                for job_id, job in self.jobs.items()
                if job.status in ("done", "failed")
            ]
            for job_id in finished_ids:
                del self.jobs[job_id]

        with self.db_lock:
            cur = self.db.execute(
                """
                UPDATE downloads
                SET cleared = 1
                WHERE cleared = 0 AND status IN ('done', 'failed')
                """
            )
            self.db.commit()
            return int(cur.rowcount)

    def clear_history(self) -> int:
        with self.lock:
            finished_ids = [
                job_id
                for job_id, job in self.jobs.items()
                if job.status in ("done", "failed")
            ]
            for job_id in finished_ids:
                del self.jobs[job_id]

            with self.db_lock:
                cur = self.db.execute("DELETE FROM downloads WHERE status IN ('done', 'failed')")
                self.db.commit()
                return int(cur.rowcount)

    def _persist_job(self, job: DownloadJob) -> None:
        with self.db_lock:
            self.db.execute(
                """
                INSERT OR REPLACE INTO downloads (
                    id, source_url, resolved_url, media_type, folder_name,
                    status, error, created_at, started_at, finished_at, cleared
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT cleared FROM downloads WHERE id = ?), 0))
                """,
                (
                    job.id,
                    job.source_url,
                    job.resolved_url,
                    job.media_type,
                    job.folder_name,
                    job.status,
                    job.error,
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                    job.id,
                ),
            )
            self.db.commit()

    def get_settings(self) -> dict:
        return {
            "gap_seconds": self.gap_seconds,
            "output_base": self.output_base,
            "download_root": str(self.download_root) if self.restricted else None,
            "cookies_path": self.cookies_path,
            "cookies_exists": Path(self.cookies_path).exists(),
        }

    def update_settings(self, gap_seconds: Optional[int] = None, output_base: Optional[str] = None) -> dict:
        if gap_seconds is not None:
            self.gap_seconds = max(0, min(3600, int(gap_seconds)))
        if output_base is not None and output_base.strip():
            self.output_base = self._validate_output_base(output_base.strip())
        Path(self.output_base).mkdir(parents=True, exist_ok=True)
        self._save_runtime_settings()
        return self.get_settings()

    def update_cookies(self, uploaded_text: str) -> dict:
        if not uploaded_text.strip():
            raise ValueError("Uploaded cookie file is empty")
        Path(self.cookies_path).write_text(uploaded_text, encoding="utf-8")
        self._save_runtime_settings()
        return self.get_settings()

    def import_cookies_file(self, file_path: str | Path) -> dict:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        return self.update_cookies(text)

    def _ensure_deps_once(self) -> None:
        with self._deps_lock:
            if self._deps_checked:
                return
            self.setup_message = "Installing missing dependencies (ffmpeg / JS runtime)..."
            try:
                ok, detail = ensure_dependencies()
            except Exception as exc:
                ok, detail = False, str(exc)
            self.setup_message = "" if ok else detail
            # Only stop re-checking once everything is present or setup has been attempted.
            self._deps_checked = True

    def _queue_agent_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.inbox_queue.get(timeout=1)
            except queue.Empty:
                continue

            self._ensure_deps_once()
            try:
                expanded_urls = self._expand_to_entries(item.url)
                for resolved_url in expanded_urls:
                    job = DownloadJob(
                        id=str(uuid.uuid4()),
                        source_url=item.url,
                        resolved_url=resolved_url,
                        media_type=item.media_type,
                        folder_name=item.folder_name,
                    )
                    with self.lock:
                        self.jobs[job.id] = job
                    self._persist_job(job)
                    self.download_queue.put(job)
            except Exception as exc:
                failed_job = DownloadJob(
                    id=str(uuid.uuid4()),
                    source_url=item.url,
                    resolved_url=item.url,
                    media_type=item.media_type,
                    folder_name=item.folder_name,
                    status="failed",
                    error=str(exc),
                    started_at=datetime.now(timezone.utc).isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                with self.lock:
                    self.jobs[failed_job.id] = failed_job
                self._persist_job(failed_job)
            finally:
                self.inbox_queue.task_done()

    def _download_agent_loop(self) -> None:
        while not self.stop_event.is_set():
            if not self.run_event.wait(timeout=1):
                continue
            try:
                job = self.download_queue.get(timeout=1)
            except queue.Empty:
                continue

            # Paused between dequeue and start: hold the job until resumed.
            while not self.run_event.wait(timeout=1):
                if self.stop_event.is_set():
                    return

            self._ensure_deps_once()
            with self.lock:
                tracked = self.jobs.get(job.id)
                if tracked:
                    tracked.status = "downloading"
                    tracked.started_at = datetime.now(timezone.utc).isoformat()
                    self._persist_job(tracked)

            success, err = self._run_download(job)
            with self.lock:
                tracked = self.jobs.get(job.id)
                if tracked:
                    tracked.status = "done" if success else "failed"
                    tracked.error = "" if success else err
                    tracked.finished_at = datetime.now(timezone.utc).isoformat()
                    self._persist_job(tracked)

            self.download_queue.task_done()
            if not self.stop_event.is_set() and self.gap_seconds > 0:
                self.stop_event.wait(self.gap_seconds)

    def _expand_to_entries(self, url: str) -> List[str]:
        if not Path(self.cookies_path).exists():
            raise RuntimeError(f"cookies file not found at {self.cookies_path}")

        cmd = [
            *_ytdlp_cmd(),
            "--flat-playlist",
            "--skip-download",
            "--no-warnings",
            "--print",
            "%(webpage_url)s",
            *_js_runtime_args(),
            "--cookies",
            self.cookies_path,
            url,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, creationflags=_SUBPROCESS_FLAGS, env=_subprocess_env()
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Unknown error").strip()
            raise RuntimeError(f"Failed to resolve URL: {detail}")

        entries = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not entries:
            return [url]
        return list(dict.fromkeys(entries))

    def _run_download(self, job: DownloadJob) -> tuple[bool, str]:
        base = Path(self.output_base).resolve()
        target_dir = (base / job.folder_name).resolve()
        if target_dir != base and base not in target_dir.parents:
            return False, "Folder name must stay inside the download folder"
        target_dir.mkdir(parents=True, exist_ok=True)

        if job.media_type == "audio":
            cmd = [
                *_ytdlp_cmd(),
                "-x",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "0",
                "--embed-thumbnail",
                "--add-metadata",
                "--cookies",
                self.cookies_path,
                "--output",
                str(target_dir / "%(title)s.%(ext)s"),
                job.resolved_url,
            ]
        else:
            cmd = [
                *_ytdlp_cmd(),
                "-f",
                "bv*+ba/b",
                "--merge-output-format",
                "mp4",
                "--add-metadata",
                "--cookies",
                self.cookies_path,
                "--output",
                str(target_dir / "%(title)s.%(ext)s"),
                job.resolved_url,
            ]

        cmd += _js_runtime_args()
        result = subprocess.run(
            cmd, capture_output=True, text=True, creationflags=_SUBPROCESS_FLAGS, env=_subprocess_env()
        )
        if result.returncode == 0:
            return True, ""
        detail = (result.stderr or result.stdout or "Unknown download error").strip()
        return False, detail[-1200:]
