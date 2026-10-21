#!/usr/bin/env python3
"""
cleanup.py — Fix filenames, set metadata tags, remove empty folders, handle jukebox splits.

Usage:
  python3 cleanup.py                       # clean output_base from artists.yaml
  python3 cleanup.py /path/to/music/dir    # clean specific directory
"""

import os, re, sys
from pathlib import Path
import yaml

SCRIPT_DIR = Path(__file__).parent
PIPELINE_DIR = SCRIPT_DIR.parent

def load_config():
    config_path = PIPELINE_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}

CONFIG = load_config()
cleanup_cfg = CONFIG.get("cleanup", {})

try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, TIT2, TALB, TPE1, TRCK
    HAS_MUTAGEN = True
except ImportError:
    print("Warning: mutagen not installed. Metadata fixing disabled.")
    HAS_MUTAGEN = False

SPECIAL_CHARS = re.compile(r'[｜：＜＞？＊｀＂｀｛｝]')
ASCII_BAD = re.compile(r'[|:<>?*`"{}]')

def fix_filename(path):
    if not cleanup_cfg.get("fix_filenames", True):
        return path
    dirn = os.path.dirname(path)
    base = os.path.basename(path)
    fixed = SPECIAL_CHARS.sub('', base)
    fixed = ASCII_BAD.sub('', fixed)
    fixed = re.sub(r'\s+', ' ', fixed).strip()
    if fixed != base:
        new_path = os.path.join(dirn, fixed)
        if not os.path.exists(new_path):
            os.rename(path, new_path)
            print(f"  Renamed: {base} → {fixed}")
            return new_path
    return path

def set_metadata(mp3_path, title=None, album=None, artist=None, track_num=None):
    if not HAS_MUTAGEN or not cleanup_cfg.get("fix_metadata", True):
        return
    try:
        try:
            tags = ID3(mp3_path)
        except:
            from mutagen.id3 import ID3NoHeaderError
            tags = ID3()
        if title:
            tags['TIT2'] = TIT2(encoding=3, text=title)
        if album:
            tags['TALB'] = TALB(encoding=3, text=album)
        if artist:
            tags['TPE1'] = TPE1(encoding=3, text=artist)
        if track_num:
            tags['TRCK'] = TRCK(encoding=3, text=str(track_num))
        tags.save(mp3_path)
    except Exception as e:
        print(f"  Warning: Could not set metadata on {mp3_path}: {e}")

def infer_metadata_from_path(mp3_path, music_root):
    rel = os.path.relpath(mp3_path, music_root)
    parts = rel.split(os.sep)
    title = os.path.splitext(parts[-1])[0]
    title = re.sub(r'^\d+\s*[-–.]\s*', '', title).strip()
    album = parts[-2] if len(parts) >= 2 else ""
    album = album.replace("_", " ")
    artist = parts[-3] if len(parts) >= 3 else parts[0] if parts else ""
    artist = artist.replace("_", " ")
    return title, album, artist

def remove_empty_dirs(root):
    if not cleanup_cfg.get("delete_empty_folders", True):
        return 0
    removed = 0
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if dirpath == root:
            continue
        if not os.listdir(dirpath):
            os.rmdir(dirpath)
            print(f"  Removed empty dir: {dirpath}")
            removed += 1
    return removed

def check_jukebox_split(folder):
    if not cleanup_cfg.get("delete_jukebox_if_split", True):
        return
    min_tracks = cleanup_cfg.get("min_split_tracks", 3)
    tracks_dir = os.path.join(folder, "tracks")
    if not os.path.isdir(tracks_dir):
        return
    track_files = [f for f in os.listdir(tracks_dir) if f.lower().endswith(".mp3")]
    if len(track_files) >= min_tracks:
        parent_mp3s = [f for f in os.listdir(folder) if f.lower().endswith(".mp3")]
        for mp3 in parent_mp3s:
            mp3_path = os.path.join(folder, mp3)
            print(f"  Removing jukebox (already split): {mp3_path}")
            os.remove(mp3_path)

def clean_directory(music_root):
    print(f"\nCleaning: {music_root}")
    if not os.path.isdir(music_root):
        print(f"  Directory not found: {music_root}")
        return

    fixed_names = 0
    fixed_meta = 0

    for dirpath, dirnames, filenames in os.walk(music_root):
        check_jukebox_split(dirpath)
        for fname in filenames:
            if not fname.lower().endswith(".mp3"):
                continue
            fpath = os.path.join(dirpath, fname)
            new_path = fix_filename(fpath)
            if new_path != fpath:
                fixed_names += 1
                fpath = new_path
            title, album, artist = infer_metadata_from_path(fpath, music_root)
            if title and album and artist:
                set_metadata(fpath, title=title, album=album, artist=artist)
                fixed_meta += 1

    removed_dirs = remove_empty_dirs(music_root)
    print(f"  Fixed filenames: {fixed_names}")
    print(f"  Updated metadata: {fixed_meta}")
    print(f"  Removed empty dirs: {removed_dirs}")

def main():
    if len(sys.argv) > 1:
        clean_directory(sys.argv[1])
    else:
        config_file = PIPELINE_DIR / "artists.yaml"
        with open(config_file) as f:
            config = yaml.safe_load(f)
        output_base = config.get("output_base",
            CONFIG.get("paths", {}).get("output_base", "/media/disks/nas/music"))
        clean_directory(output_base)

if __name__ == "__main__":
    main()
