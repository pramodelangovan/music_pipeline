#!/usr/bin/env python3
"""HTTP API: a thin wrapper over the shared core.DownloadManager."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core import DownloadManager, QueueItem, ResearchManager


class QueueItemInput(BaseModel):
    url: str = Field(min_length=5)
    media_type: Literal["audio", "video"] = "audio"
    folder_name: str = Field(min_length=1, max_length=100)


class ResearchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aliases: List[str] = Field(default_factory=list, max_length=10)
    known_albums: List[str] = Field(default_factory=list, max_length=30)
    fetch_singles: bool = True
    fetch_unknown_albums: bool = True


class QueueRequest(BaseModel):
    items: List[QueueItemInput]


class UpdateSettingsRequest(BaseModel):
    gap_seconds: Optional[int] = Field(default=None, ge=0, le=3600)
    output_base: Optional[str] = Field(default=None, max_length=500)


manager = DownloadManager()
research = ResearchManager(lambda: manager.cookies_path)
LOGS_DIR = manager.settings_path.parent.resolve()
LOGS_DIR.mkdir(parents=True, exist_ok=True)

api_logger = logging.getLogger("music_pipeline.api")
api_logger.setLevel(logging.INFO)
api_logger.propagate = False
if not any(
    isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == LOGS_DIR / "app.log"
    for handler in api_logger.handlers
):
    file_handler = logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    api_logger.addHandler(file_handler)

app = FastAPI(title="Music Pipeline API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request, call_next):
    started_at = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        api_logger.exception("%s %s failed", request.method, request.url.path)
        raise

    if request.method not in {"GET", "HEAD"} or response.status_code >= 400:
        elapsed = time.monotonic() - started_at
        api_logger.info(
            "%s %s %s %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
    return response


@app.on_event("startup")
def startup() -> None:
    manager.start()
    # Agent-based: pick up unfinished downloads and research after a container restart/crash.
    if os.environ.get("MP_AUTORESUME", "1") != "0":
        recovered = manager.resume() if manager.has_active_work() else 0
        resumed = research.resume_interrupted()
        api_logger.info("Auto-resume: %d download job(s) recovered, research resumed=%s", recovered, resumed)
    api_logger.info("Music Pipeline API started")


@app.on_event("shutdown")
def shutdown() -> None:
    research.interrupt()
    manager.stop()
    api_logger.info("Music Pipeline API stopped")


def _resolve_logs_path(relative_path: str) -> Path:
    resolved = (LOGS_DIR / relative_path).resolve()
    try:
        resolved.relative_to(LOGS_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path must stay inside the logs folder")
    return resolved


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/logs")
def list_logs(path: str = "") -> dict:
    directory = _resolve_logs_path(path)
    if not directory.is_dir():
        raise HTTPException(status_code=404, detail="Logs folder not found")

    entries = []
    try:
        for entry in directory.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_dir():
                entries.append({"name": entry.name, "type": "directory"})
            elif entry.is_file() and entry.suffix.lower() == ".log":
                stat = entry.stat()
                entries.append(
                    {
                        "name": entry.name,
                        "type": "file",
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    }
                )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to list logs folder: {exc}")

    entries.sort(key=lambda item: (item["type"] != "directory", item["name"].casefold()))
    return {"path": path, "entries": entries}


@app.get("/api/logs/content")
def read_log(path: str, lines: int = Query(default=200, ge=1, le=1000)) -> dict:
    log_file = _resolve_logs_path(path)
    if log_file.suffix.lower() != ".log":
        raise HTTPException(status_code=400, detail="Only .log files can be viewed")
    if not log_file.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    max_bytes = 512 * 1024
    try:
        with log_file.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            offset = max(0, size - max_bytes)
            stream.seek(offset)
            content = stream.read(max_bytes).decode("utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to read log file: {exc}")

    return {
        "path": path,
        "content": "\n".join(content.splitlines()[-lines:]),
        "truncated": offset > 0,
    }


@app.get("/api/jobs")
def jobs() -> dict:
    return manager.jobs_snapshot()


@app.get("/api/history")
def history(limit: int = 1000) -> dict:
    safe_limit = max(1, min(limit, 5000))
    return {"history": manager.list_history(limit=safe_limit)}


@app.post("/api/jobs/clear")
def clear_jobs() -> dict:
    return {"cleared": manager.clear_recent()}


@app.post("/api/jobs/clear-all")
def clear_all_jobs() -> dict:
    return {"cleared": manager.clear_all()}


@app.post("/api/jobs/retry-failed")
def retry_failed_jobs() -> dict:
    return {"retried": manager.retry_failed()}


@app.post("/api/history/clear")
def clear_history() -> dict:
    return {"cleared": manager.clear_history()}


@app.post("/api/queue")
def enqueue(payload: QueueRequest) -> dict:
    if not payload.items:
        raise HTTPException(status_code=400, detail="No queue items provided")
    items = [QueueItem(i.url, i.media_type, i.folder_name) for i in payload.items]
    result = manager.submit(items)
    return {"message": "Queued for processing", **result}


@app.post("/api/queue/pause")
def pause_queue() -> dict:
    manager.pause()
    return {"paused": manager.paused}


@app.post("/api/queue/start")
def start_queue() -> dict:
    recovered = manager.resume()
    return {"paused": manager.paused, "recovered": recovered}


@app.get("/api/research")
def research_status() -> dict:
    return research.snapshot()


@app.post("/api/research")
def research_start(payload: ResearchRequest) -> dict:
    try:
        research.start(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return research.snapshot()


@app.post("/api/research/cancel")
def research_cancel() -> dict:
    research.cancel()
    return {"cancelling": True}


@app.get("/api/settings")
def get_settings() -> dict:
    return manager.get_settings()


@app.put("/api/settings")
def set_settings(payload: UpdateSettingsRequest) -> dict:
    try:
        return manager.update_settings(payload.gap_seconds, payload.output_base)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/settings/cookies")
async def upload_cookies(file: UploadFile = File(...)) -> dict:
    body = await file.read()
    text = body.decode("utf-8", errors="ignore")
    try:
        return manager.update_cookies(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        api_logger.exception("Unable to save uploaded cookies")
        raise HTTPException(status_code=500, detail=f"Unable to save cookies: {exc}")
