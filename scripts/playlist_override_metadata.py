#!/usr/bin/env python3
"""Resolve explicit playlist metadata overrides before writing MP3 tags."""

import argparse
import os
from pathlib import Path

import yaml


def normalize_title(value):
    return value.strip() if value else ""


def load_overrides(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    overrides = {}
    for playlist in data.get("playlists", []):
        playlist_id = playlist.get("id")
        if playlist_id:
            entry = {
                "name": playlist.get("name", ""),
                "artist": playlist.get("artist", ""),
                "album": playlist.get("album", ""),
                "cover": playlist.get("cover", ""),
            }
            for track in playlist.get("tracks", []):
                title = normalize_title(track.get("title", ""))
                if title:
                    entry.setdefault("tracks", {})
                    entry["tracks"][title] = {
                        "title": title,
                        "artist": track.get("artist") or entry["artist"],
                        "album": track.get("album") or entry["album"],
                    }
            overrides[playlist_id] = entry
    return overrides


def find_playlist_match(playlist_url, overrides):
    for playlist_id, values in overrides.items():
        if playlist_id in playlist_url:
            return values
    return {}


def main():
    parser = argparse.ArgumentParser(description="Load explicit playlist metadata overrides.")
    parser.add_argument("playlist_url", help="YouTube playlist URL")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "playlist_metadata.yaml"), help="Path to playlist override config")
    args = parser.parse_args()

    overrides = load_overrides(args.config)
    match = find_playlist_match(args.playlist_url, overrides)
    print(match)


if __name__ == "__main__":
    raise SystemExit(main())
