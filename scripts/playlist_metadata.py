#!/usr/bin/env python3
"""Apply metadata tags to a downloaded MP3 album folder."""

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

from playlist_utils import apply_mp3_metadata, get_logs_dir


def iter_mp3_files(root):
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".mp3"):
                yield os.path.join(dirpath, name)


def main():
    parser = argparse.ArgumentParser(description="Apply album, artist, and cover metadata to all MP3s in a folder.")
    parser.add_argument("folder", help="Folder containing MP3 files")
    parser.add_argument("--artist", default="Unknown Artist", help="Artist name to tag")
    parser.add_argument("--album", default="Unknown Album", help="Album name to tag")
    parser.add_argument("--cover", default="", help="Optional cover image file to embed")
    args = parser.parse_args()

    logs_dir = get_logs_dir(Path(__file__).resolve().parent.parent)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"playlist_metadata_{ts}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    mp3_files = sorted(iter_mp3_files(args.folder))
    for index, mp3_path in enumerate(mp3_files, start=1):
        title = os.path.splitext(os.path.basename(mp3_path))[0]
        apply_mp3_metadata(
            mp3_path,
            title=title,
            artist=args.artist,
            album=args.album,
            track_number=index,
            cover_path=args.cover,
        )
        logging.info("Tagged: %s", mp3_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
