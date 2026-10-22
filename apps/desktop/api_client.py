import os
from typing import Any, Dict, List

import requests


class ApiClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("MP_API_BASE", "http://127.0.0.1:8000")).rstrip("/")

    def set_base_url(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _ensure_json(self, response: requests.Response) -> Dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        text = response.text.strip()
        raise RuntimeError(text or f"Unexpected response ({response.status_code})")

    def get_jobs(self) -> Dict[str, Any]:
        r = requests.get(self._url("/api/jobs"), timeout=20)
        payload = self._ensure_json(r)
        if not r.ok:
            raise RuntimeError(payload.get("detail", "Failed to load jobs"))
        return payload

    def get_history(self, limit: int = 500) -> Dict[str, Any]:
        r = requests.get(self._url(f"/api/history?limit={limit}"), timeout=20)
        payload = self._ensure_json(r)
        if not r.ok:
            raise RuntimeError(payload.get("detail", "Failed to load history"))
        return payload

    def queue_items(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        r = requests.post(self._url("/api/queue"), json={"items": items}, timeout=40)
        payload = self._ensure_json(r)
        if not r.ok:
            raise RuntimeError(payload.get("detail", "Failed to queue items"))
        return payload

    def clear_recent(self) -> Dict[str, Any]:
        r = requests.post(self._url("/api/jobs/clear"), timeout=20)
        payload = self._ensure_json(r)
        if not r.ok:
            raise RuntimeError(payload.get("detail", "Failed to clear jobs"))
        return payload

    def get_settings(self) -> Dict[str, Any]:
        r = requests.get(self._url("/api/settings"), timeout=20)
        payload = self._ensure_json(r)
        if not r.ok:
            raise RuntimeError(payload.get("detail", "Failed to load settings"))
        return payload

    def update_settings(self, gap_seconds: int) -> Dict[str, Any]:
        r = requests.put(self._url("/api/settings"), json={"gap_seconds": gap_seconds}, timeout=20)
        payload = self._ensure_json(r)
        if not r.ok:
            raise RuntimeError(payload.get("detail", "Failed to update settings"))
        return payload

    def upload_cookies(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, "rb") as fh:
            files = {"file": (os.path.basename(file_path), fh, "text/plain")}
            r = requests.post(self._url("/api/settings/cookies"), files=files, timeout=60)
        payload = self._ensure_json(r)
        if not r.ok:
            raise RuntimeError(payload.get("detail", "Failed to upload cookies"))
        return payload
