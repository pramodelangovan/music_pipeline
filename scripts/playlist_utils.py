#!/usr/bin/env python3
"""Shared helpers for YouTube Music playlist downloads and mp3 metadata tags."""

import os
import re
import subprocess
from pathlib import Path


def get_logs_dir(project_root):
    config = load_config(project_root)
    logs_dir = Path(project_root) / config.get("paths", {}).get("logs", "logs")
    logs_dir.mkdir(exist_ok=True, parents=True)
    return logs_dir

try:
    from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TRCK
    HAS_MUTAGEN = True
except ImportError:  # pragma: no cover
    HAS_MUTAGEN = False


def load_config(project_root):
    config_path = Path(project_root) / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def safe_name(value):
    value = (value or "").strip()
    value = re.sub(r"[\\/:*?\"<>|]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def build_ytdlp_download_command(playlist_url, output_dir, cookies_path, album_name=None, artist_name=None):
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--embed-thumbnail",
        "--add-metadata",
        "--no-overwrites",
        "--cookies",
        cookies_path,
        "--output",
        output_template,
        playlist_url,
    ]
    return cmd


def build_tag_map(title, artist, album, track_number=None, cover_path=None):
    tags = {
        "title": title,
        "artist": artist,
        "album": album,
    }
    if track_number is not None:
        tags["track_number"] = int(track_number)
    if cover_path:
        tags["cover_path"] = cover_path
    return tags


def apply_mp3_metadata(mp3_path, title=None, artist=None, album=None, track_number=None, cover_path=None):
    if not HAS_MUTAGEN or not os.path.exists(mp3_path):
        return False, "mutagen missing or file not found"

    try:
        try:
            id3 = ID3(mp3_path)
        except Exception:
            id3 = ID3()

        wrote = []
        if title:
            id3["TIT2"] = TIT2(encoding=3, text=title)
            wrote.append("title")
        if album:
            id3["TALB"] = TALB(encoding=3, text=album)
            wrote.append("album")
        if artist:
            id3["TPE1"] = TPE1(encoding=3, text=artist)
            wrote.append("artist")
        if track_number is not None:
            id3["TRCK"] = TRCK(encoding=3, text=str(track_number))
            wrote.append("track_number")

        if cover_path and os.path.exists(cover_path):
            with open(cover_path, "rb") as fh:
                data = fh.read()
            id3["APIC"] = APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,
                desc="Cover",
                data=data,
            )
            wrote.append("cover")

        id3.save(mp3_path)
        return True, ", ".join(wrote) if wrote else "no tags written"
    except Exception as exc:
        return False, str(exc)


def playlist_entry_title_url(playlist_url, cookies_path):
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--no-warnings",
        "--print",
        "%(id)s\t%(title)s\t%(webpage_url)s",
        "--cookies",
        cookies_path,
        playlist_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []

    entries = []
    for line in result.stdout.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) >= 3 and parts[0] and parts[1]:
            entries.append({"id": parts[0], "title": parts[1], "url": parts[2]})
    return entries


def download_single_track(url, output_dir, cookies_path, artist_name=None, album_name=None):
    command = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--embed-thumbnail",
        "--add-metadata",
        "--no-overwrites",
        "--cookies",
        cookies_path,
        "--remote-components",
        "ejs:github",
        "--js-runtimes",
        "deno",
        "--output",
        os.path.join(output_dir, "%(title)s.%(ext)s"),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    payload = (result.stderr or "") + "\n" + (result.stdout or "")
    return result.returncode == 0, payload.strip()
