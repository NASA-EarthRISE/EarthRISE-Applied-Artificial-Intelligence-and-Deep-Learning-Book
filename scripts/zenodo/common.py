import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent.parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
SUMMARY_PATH = SCRIPT_DIR / "zenodo_summary.json"
# Sandbox runs record here (gitignored) so a rehearsal never touches the
# committed summary.
SANDBOX_SUMMARY_PATH = SCRIPT_DIR / "zenodo_summary.sandbox.json"
# A chapter created by create.py but not yet submitted for review.
DRAFT_STATUS = "draft"

# Cell ids in chapter notebooks. "author-attribution" prints the author list
# in the PDF; "author-notes" optionally follows it (e.g. equal contribution).
AUTHOR_CELL_ID = "author-attribution"
AUTHOR_NOTES_CELL_ID = "author-notes"

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


def summary_path(sandbox: bool) -> Path:
    return SANDBOX_SUMMARY_PATH if sandbox else SUMMARY_PATH


def filter_chapters(chapters: list[dict], chapter_id: str | None) -> list[dict]:
    if chapter_id is None:
        return chapters
    matched = [ch for ch in chapters if ch["id"] == chapter_id]
    if not matched:
        sys.exit(f"ERROR: '{chapter_id}' not found in config.yaml")
    return matched


def chapter_sort_key(ch: dict) -> tuple[int, ...]:
    return tuple(int(x) for x in ch["id"].removeprefix("ch").split("."))


def pdf_upload_name(ch: dict, book_config: dict) -> str | None:
    """Zenodo file name for the chapter PDF, matching the chapters deposited in June 2026."""
    prefix = book_config.get("pdf_prefix", "")
    if prefix and ch.get("pdf_folder"):
        return f"{prefix}_{ch['pdf_folder']}.pdf"
    return None


def find_chapter_pdf(ch: dict, repo_dir: Path, pdf_dir: Path | None = None) -> Path | None:
    """Find the chapter PDF. Checks _book/ first (Quarto profile output),
    then falls back to --pdf-dir if provided."""
    stem = Path(ch["notebook"]).stem
    book_pdf = repo_dir / "_book" / f"{stem}.pdf"
    if book_pdf.exists():
        return book_pdf

    if pdf_dir:
        folder = pdf_dir / ch["pdf_folder"]
        if folder.exists():
            pdfs = sorted(folder.glob("*.pdf"))
            if pdfs:
                return pdfs[0]

    return None


def author_cell_problem(nb_path: Path) -> str | None:
    """Why the notebook is not ready to deposit, or None if it has the author cell."""
    try:
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"cannot read {nb_path.name}: {exc}"
    if not any(cell.get("id") == AUTHOR_CELL_ID for cell in nb.get("cells", [])):
        return f"{nb_path.name} has no '{AUTHOR_CELL_ID}' cell, so its PDF would have no author list"
    return None


def find_chapter_notebooks(ch: dict, repo_dir: Path) -> list[Path]:
    notebook_dir = (repo_dir / ch["notebook"]).parent
    if not notebook_dir.exists():
        return []
    return sorted(notebook_dir.glob("*.ipynb"))


def preflight(config: dict, pdf_dir: Path | None, chapter_id: str | None) -> bool:
    """Report author and file readiness for each selected chapter. Purely
    informational: run() decides what is actually fatal."""
    chapters = filter_chapters(config["chapters"], chapter_id)
    all_ok = True

    print("\nPreflight check")
    print("-" * 60)

    for ch in chapters:
        print(f"\n[{ch['id']}] {ch['title'][:60]}")

        authors = ch.get("authors") or []
        if authors:
            print(f"  Authors: {', '.join(a['name'] for a in authors)}")
        else:
            print("  Authors: MISSING")
            all_ok = False

        pdf = find_chapter_pdf(ch, REPO_DIR, pdf_dir)
        if pdf:
            print(f"  PDF: {pdf.name}")
        else:
            print(f"  PDF: not found (render with: python scripts/zenodo/render_pdf.py {ch['id']})")

        notebooks = find_chapter_notebooks(ch, REPO_DIR)
        for nb in notebooks:
            print(f"  Notebook: {nb.name}")
        if not notebooks:
            print("  Notebook: none found")

        problem = author_cell_problem(REPO_DIR / ch["notebook"])
        print(f"  Author cell: {'found' if problem is None else 'MISSING (' + problem + ')'}")
        if problem:
            all_ok = False

        if not pdf and not notebooks:
            print("  WARNING: nothing to upload for this chapter")
            all_ok = False

    print()
    return all_ok
