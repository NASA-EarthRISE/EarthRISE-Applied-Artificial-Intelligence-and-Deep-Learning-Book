import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent.parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
SUMMARY_PATH = SCRIPT_DIR / "zenodo_summary.json"

load_dotenv(REPO_DIR / ".env")


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        sys.exit(f"ERROR: config not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_summary(path: Path = SUMMARY_PATH) -> dict:
    if not path.exists():
        return {"book": {}, "chapters": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_summary(data: dict, path: Path = SUMMARY_PATH):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def filter_chapters(chapters: list[dict], chapter_id: str | None) -> list[dict]:
    if chapter_id is None:
        return chapters
    matched = [ch for ch in chapters if ch["id"] == chapter_id]
    if not matched:
        sys.exit(f"ERROR: '{chapter_id}' not found in config.yaml")
    return matched


def chapter_sort_key(ch: dict) -> tuple[int, ...]:
    return tuple(int(x) for x in ch["id"].removeprefix("ch").split("."))
