#!/usr/bin/env python3
"""Download a YouTube Music playlist as MP3s and stamp artist/album metadata."""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from metadata_enricher import enrich_track_metadata, normalize_title
from playlist_override_metadata import find_playlist_match, load_overrides
from playlist_utils import (
    apply_mp3_metadata,
    download_single_track,
    get_logs_dir,
    load_config,
    playlist_entry_title_url,
    safe_name,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parent
CONFIG = load_config(PIPELINE_DIR)
LOGS_DIR = get_logs_dir(PIPELINE_DIR)
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOGS_DIR / f"playlist_download_{TS}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
LOGGER = logging.getLogger("playlist_download")


def default_output_dir():
    path = CONFIG.get("playlist", {}).get("output_base") or os.path.join(PIPELINE_DIR, "downloads")
    return str(Path(path).expanduser())


def ensure_cookies(cookies_path):
    if not cookies_path or not os.path.exists(cookies_path):
        raise FileNotFoundError(
            "Missing cookies.txt. Export browser cookies and set config.yaml paths.cookies or pass --cookies."
        )


def find_cover_for_album(album_dir, preferred_cover=None):
    if preferred_cover and os.path.exists(preferred_cover):
        return preferred_cover
    candidates = [
        "cover.jpg",
        "cover.png",
        "folder.jpg",
        "folder.png",
        "art.jpg",
        "art.png",
    ]
    for candidate in candidates:
        full = os.path.join(album_dir, candidate)
        if os.path.exists(full):
            return full
    return None


def stamp_playlist_files(album_dir, artist_name, album_name, cover_path=None, track_metadata=None):
    track_metadata = track_metadata or {}
    mp3_files = sorted(
        [
            os.path.join(album_dir, name)
            for name in os.listdir(album_dir)
            if name.lower().endswith(".mp3")
        ]
    )
    for index, mp3_path in enumerate(mp3_files, start=1):
        title = os.path.splitext(os.path.basename(mp3_path))[0]
        title = re.sub(r"^\d+\s*[-–.]\s*", "", title)
        metadata = track_metadata.get(title) or track_metadata.get(os.path.basename(mp3_path)) or {
            "title": title,
            "artist": artist_name or "Unknown Artist",
            "album": album_name or "Unknown Album",
        }
        ok, detail = apply_mp3_metadata(
            mp3_path,
            title=metadata.get("title") or title,
            artist=metadata.get("artist") or (artist_name or "Unknown Artist"),
            album=metadata.get("album") or (album_name or "Unknown Album"),
            track_number=index,
            cover_path=cover_path,
        )
        if ok:
            LOGGER.info("Tagged %s: %s", mp3_path, detail)
        else:
            LOGGER.warning("Metadata write failed for %s: %s", mp3_path, detail)


def main():
    parser = argparse.ArgumentParser(description="Download a YouTube Music playlist as MP3 files with album metadata.")
    parser.add_argument("playlist_url", help="YouTube Music playlist URL")
    parser.add_argument("--artist", default="", help="Artist name to write into metadata")
    parser.add_argument("--album", default="", help="Album name to write into metadata")
    parser.add_argument("--output-dir", default=default_output_dir(), help="Directory for downloaded MP3 files")
    parser.add_argument("--cookies", default=str(Path(PIPELINE_DIR) / CONFIG.get("paths", {}).get("cookies", "cookies.txt")), help="Path to cookies.txt")
    parser.add_argument("--cover", default="", help="Optional local cover image file for album art")
    args = parser.parse_args()

    ensure_cookies(args.cookies)

    playlist_name = args.album or "youtube_playlist"
    album_name = args.album or safe_name(playlist_name)
    artist_name = args.artist or "Unknown Artist"
    final_dir = os.path.join(args.output_dir, safe_name(artist_name), safe_name(album_name))
    os.makedirs(final_dir, exist_ok=True)

    LOGGER.info("Starting playlist download for %s", args.playlist_url)
    LOGGER.info("Artist=%s Album=%s Output=%s", artist_name, album_name, final_dir)

    override_config = Path(PIPELINE_DIR) / "playlist_metadata.yaml"
    playlist_overrides = load_overrides(str(override_config))
    playlist_match = find_playlist_match(args.playlist_url, playlist_overrides)
    if playlist_match:
        artist_name = playlist_match.get("artist") or artist_name
        album_name = playlist_match.get("album") or album_name
        LOGGER.info("Using playlist override metadata: artist=%s album=%s", artist_name, album_name)

    entries = playlist_entry_title_url(args.playlist_url, args.cookies)
    if not entries:
        LOGGER.error("No entries found in playlist: %s", args.playlist_url)
        return 1

    resolved_metadata = {}
    downloaded = 0
    for index, entry in enumerate(entries, start=1):
        track_url = entry["url"]
        playlist_track = {}
        if playlist_match:
            playlist_track = (playlist_match.get("tracks") or {}).get(normalize_title(entry["title"])) or {}
        enriched = enrich_track_metadata(
            entry["title"],
            artist_hint=playlist_track.get("artist") or (args.artist or artist_name),
            album_hint=playlist_track.get("album") or (args.album or album_name),
        )
        resolved_metadata[normalize_title(entry["title"])] = enriched
        LOGGER.info("[%s/%s] Downloading: %s", index, len(entries), entry["title"])
        LOGGER.info("Resolved metadata for %s: %s", entry["title"], enriched)
        ok, detail = download_single_track(track_url, final_dir, args.cookies, artist_name, album_name)
        if not ok:
            LOGGER.warning("Failed to download: %s", entry["title"])
            if detail:
                LOGGER.warning("yt-dlp detail for %s:\n%s", entry["title"], detail[-2000:])
            continue
        downloaded += 1

    cover_path = args.cover or find_cover_for_album(final_dir)
    stamp_playlist_files(final_dir, artist_name, album_name, cover_path=cover_path, track_metadata=resolved_metadata)
    summary = {
        "playlist_url": args.playlist_url,
        "artist": artist_name,
        "album": album_name,
        "output_dir": final_dir,
        "downloaded_tracks": downloaded,
        "log_file": str(LOG_FILE),
    }
    (LOGS_DIR / f"playlist_summary_{TS}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    LOGGER.info("Done. Files saved to: %s", final_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
