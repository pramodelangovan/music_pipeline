#!/usr/bin/env python3
"""
research.py — Research artists on YouTube/YT Music and write download_plan.yaml.
Thin CLI over core.research (shared with the API and desktop app).

Usage:
  python3 scripts/research.py                   # research all artists in artists.yaml
  python3 scripts/research.py "Paul Thangiah"   # research a matching artist from artists.yaml
"""

import sys
import time
from pathlib import Path

import yaml

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from core.queue_manager import CONFIG_PATH  # noqa: E402
from core.research import research_artist  # noqa: E402

PLAN_FILE = PIPELINE_DIR / "download_plan.yaml"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def main() -> None:
    config = load_yaml(CONFIG_PATH)
    cookies = str(PIPELINE_DIR / config.get("paths", {}).get("cookies", "cookies.txt"))

    artists_file = PIPELINE_DIR / "artists.yaml"
    if not artists_file.exists():
        print(f"{artists_file.name} not found. Create it, or use the Research tab in the desktop/web app.")
        sys.exit(1)
    artists_cfg = load_yaml(artists_file)
    output_base = artists_cfg.get("output_base", config.get("paths", {}).get("output_base", "downloads"))
    artists = artists_cfg.get("artists", [])

    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target != "all":
        artists = [a for a in artists if target.lower() in a["name"].lower()]
        if not artists:
            print(f"No artist matching '{target}' found in artists.yaml")
            sys.exit(1)

    existing_plan = {a["name"]: a for a in load_yaml(PLAN_FILE).get("artists", [])}

    plan_artists = []
    for artist_cfg in artists:
        result = research_artist(artist_cfg, cookies_path=cookies)
        entry = {
            "name": result["name"],
            "output_dir": str(Path(output_base) / result["folder_name"]),
            "items": result["items"],
        }
        previous = existing_plan.get(entry["name"])
        if previous:
            known_ids = {i["id"] for i in previous.get("items", [])}
            entry["items"] = previous["items"] + [i for i in entry["items"] if i["id"] not in known_ids]
        plan_artists.append(entry)
        time.sleep(5)

    plan = {"output_base": output_base, "artists": plan_artists}
    with open(PLAN_FILE, "w", encoding="utf-8") as fh:
        yaml.dump(plan, fh, allow_unicode=True, default_flow_style=False)
    print(f"\nDownload plan saved: {PLAN_FILE}")
    print(f"Total items in plan: {sum(len(a['items']) for a in plan_artists)}")


if __name__ == "__main__":
    main()
