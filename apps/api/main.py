#!/usr/bin/env python3
"""HTTP API: a thin wrapper over the shared core.DownloadManager."""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
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
    return manager.jobs_snapshot()


@app.get("/api/history")
def history(limit: int = 1000) -> dict:
    safe_limit = max(1, min(limit, 5000))
    return {"history": manager.list_history(limit=safe_limit)}


@app.post("/api/jobs/clear")
def clear_jobs() -> dict:
    return {"cleared": manager.clear_recent()}


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
