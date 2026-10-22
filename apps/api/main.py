#!/usr/bin/env python3
"""Queue-based download API for audio/video and playlists."""

from __future__ import annotations

import json
import queue
import sqlite3
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT_DIR / "config.yaml"
DEFAULT_OUTPUT_BASE = ROOT_DIR / "downloads"
RUNTIME_SETTINGS_PATH = ROOT_DIR / "logs" / "runtime_settings.json"
DB_PATH = ROOT_DIR / "logs" / "downloads.db"


class QueueItemInput(BaseModel):
    url: str = Field(min_length=5)
    media_type: Literal["audio", "video"] = "audio"
    folder_name: str = Field(min_length=1, max_length=100)


class QueueRequest(BaseModel):
    items: List[QueueItemInput]


class UpdateSettingsRequest(BaseModel):
    gap_seconds: Optional[int] = Field(default=None, ge=0, le=3600)


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
        cfg = self._load_config()
        queue_cfg = cfg.get("queue_download", {})
        self.cookies_path = str((ROOT_DIR / cfg.get("paths", {}).get("cookies", "cookies.txt")).resolve())
        configured_output = queue_cfg.get("output_base") or DEFAULT_OUTPUT_BASE
        self.output_base = self._resolve_path(configured_output)
        self.gap_seconds = int(queue_cfg.get("gap_seconds", 12))
        self._load_runtime_settings()

        self.download_queue: queue.Queue[DownloadJob] = queue.Queue()
        self.inbox_queue: queue.Queue[QueueItemInput] = queue.Queue()
        self.jobs: Dict[str, DownloadJob] = {}
        self.lock = threading.Lock()
        self.db_lock = threading.Lock()
        self.stop_event = threading.Event()

        Path(self.output_base).mkdir(parents=True, exist_ok=True)
        (ROOT_DIR / "logs").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init_db()

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
        if not RUNTIME_SETTINGS_PATH.exists():
            return
        try:
            payload = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(payload.get("gap_seconds"), int):
                self.gap_seconds = max(0, min(3600, payload["gap_seconds"]))
            if isinstance(payload.get("output_base"), str) and payload["output_base"].strip():
                self.output_base = self._resolve_path(payload["output_base"])
        except Exception:
            return

    def _save_runtime_settings(self) -> None:
        payload = {
            "gap_seconds": self.gap_seconds,
            "output_base": self.output_base,
            "cookies_path": self.cookies_path,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        RUNTIME_SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _resolve_path(self, path_value: str | Path) -> str:
        target = Path(path_value).expanduser()
        if not target.is_absolute():
            target = ROOT_DIR / target
        return str(target.resolve())

    def start(self) -> None:
        self.queue_agent.start()
        self.download_agent.start()

    def stop(self) -> None:
        self.stop_event.set()
        try:
            self.db.close()
        except Exception:
            pass

    def submit(self, items: List[QueueItemInput]) -> dict:
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
            "cookies_path": self.cookies_path,
            "cookies_exists": Path(self.cookies_path).exists(),
        }

    def update_settings(self, payload: UpdateSettingsRequest) -> dict:
        if payload.gap_seconds is not None:
            self.gap_seconds = payload.gap_seconds
        Path(self.output_base).mkdir(parents=True, exist_ok=True)
        self._save_runtime_settings()
        return self.get_settings()

    def update_cookies(self, uploaded_text: str) -> dict:
        if not uploaded_text.strip():
            raise HTTPException(status_code=400, detail="Uploaded cookie file is empty")
        Path(self.cookies_path).write_text(uploaded_text, encoding="utf-8")
        self._save_runtime_settings()
        return self.get_settings()

    def _queue_agent_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.inbox_queue.get(timeout=1)
            except queue.Empty:
                continue

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
            try:
                job = self.download_queue.get(timeout=1)
            except queue.Empty:
                continue

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
                time.sleep(self.gap_seconds)

    def _expand_to_entries(self, url: str) -> List[str]:
        if not Path(self.cookies_path).exists():
            raise RuntimeError(f"cookies file not found at {self.cookies_path}")

        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--skip-download",
            "--no-warnings",
            "--print",
            "%(webpage_url)s",
            "--cookies",
            self.cookies_path,
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Unknown error").strip()
            raise RuntimeError(f"Failed to resolve URL: {detail}")

        entries = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not entries:
            return [url]
        unique_entries = list(dict.fromkeys(entries))
        return unique_entries

    def _run_download(self, job: DownloadJob) -> tuple[bool, str]:
        target_dir = Path(self.output_base) / job.folder_name
        target_dir.mkdir(parents=True, exist_ok=True)

        if job.media_type == "audio":
            cmd = [
                "yt-dlp",
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
                "yt-dlp",
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

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return True, ""
        detail = (result.stderr or result.stdout or "Unknown download error").strip()
        return False, detail[-1200:]


manager = DownloadManager()
app = FastAPI(title="Music Pipeline Queue API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    manager.start()


@app.on_event("shutdown")
def shutdown() -> None:
    manager.stop()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/jobs")
def jobs() -> dict:
    return {
        "jobs": manager.list_jobs(),
        "pending_queue": manager.download_queue.qsize(),
        "pending_inbox": manager.inbox_queue.qsize(),
    }


@app.get("/api/history")
def history(limit: int = 1000) -> dict:
    safe_limit = max(1, min(limit, 5000))
    return {"history": manager.list_history(limit=safe_limit)}


@app.post("/api/jobs/clear")
def clear_jobs() -> dict:
    cleared = manager.clear_recent()
    return {"cleared": cleared}


@app.post("/api/queue")
def enqueue(payload: QueueRequest) -> dict:
    if not payload.items:
        raise HTTPException(status_code=400, detail="No queue items provided")
    result = manager.submit(payload.items)
    return {"message": "Queued for processing", **result}


@app.get("/api/settings")
def get_settings() -> dict:
    return manager.get_settings()


@app.put("/api/settings")
def set_settings(payload: UpdateSettingsRequest) -> dict:
    return manager.update_settings(payload)


@app.post("/api/settings/cookies")
async def upload_cookies(file: UploadFile = File(...)) -> dict:
    body = await file.read()
    text = body.decode("utf-8", errors="ignore")
    return manager.update_cookies(text)
