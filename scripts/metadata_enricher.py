#!/usr/bin/env python3
"""Metadata enrichment utilities for playlist downloads.

This module provides a lightweight metadata enrichment layer that tries to
resolve richer artist/album tags from open metadata sources before writing ID3
fields to the downloaded MP3 files.
"""

import json
import re
import urllib.parse
import urllib.request
from typing import Dict, Optional


USER_AGENT = "music_pipeline/1.0 (metadata-enricher)"


def normalize_title(value):
    value = (value or "").strip()
    value = re.sub(r"^\d+\s*[-–.]\s*", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_musicbrainz_record(record):
    if not record:
        return {}

    artist = None
    album = None
    title = record.get("title") or record.get("title", "")

    artist_credit = record.get("artist-credit") or []
    if artist_credit:
        first = artist_credit[0]
        artist = first.get("artist", {}).get("name") or first.get("name")

    releases = record.get("releases") or []
    if releases:
        album = releases[0].get("title")

    return {
        "title": title,
        "artist": artist,
        "album": album,
    }


def search_musicbrainz_recording(title, artist_hint=None):
    query_parts = [f'recording:"{title}"']
    if artist_hint:
        query_parts.insert(0, f'artist:"{artist_hint}"')
    query = " AND ".join(query_parts)
    url = "https://musicbrainz.org/ws/2/recording/?query=" + urllib.parse.quote(query) + "&fmt=json&limit=1"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.load(response)
    except Exception:
        return {}

    record = (data.get("recordings") or [{}])[0]
    return parse_musicbrainz_record(record)


def resolve_track_metadata(title, artist_hint=None, album_hint=None, api_response=None):
    normalized_title = normalize_title(title)

    metadata = {
        "title": normalized_title,
        "artist": artist_hint or "Unknown Artist",
        "album": album_hint or "Unknown Album",
    }

    if api_response:
        if api_response.get("title"):
            metadata["title"] = normalize_title(api_response.get("title"))
        if api_response.get("artist"):
            metadata["artist"] = api_response.get("artist").strip()
        if api_response.get("album"):
            metadata["album"] = api_response.get("album").strip()

    if not artist_hint and not album_hint:
        fallback = search_musicbrainz_recording(normalized_title)
        if fallback.get("artist"):
            metadata["artist"] = fallback["artist"]
        if fallback.get("album"):
            metadata["album"] = fallback["album"]

    return metadata


def enrich_track_metadata(title, artist_hint=None, album_hint=None):
    api_response = search_musicbrainz_recording(title, artist_hint)
    return resolve_track_metadata(title, artist_hint, album_hint, api_response=api_response)
