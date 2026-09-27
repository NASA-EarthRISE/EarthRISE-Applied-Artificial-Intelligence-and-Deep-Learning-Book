"""Inject Zenodo DOI badges into chapter notebooks and update citing.qmd."""

import argparse
import json
import re
import sys
from pathlib import Path

from common import (
    AUTHOR_CELL_ID,
    AUTHOR_NOTES_CELL_ID,
    REPO_DIR,
    chapter_sort_key,
    filter_chapters,
    load_config,
    load_summary,
    summary_path,
)

SENTINEL = "# zenodo-doi-injected"
BADGE_CELL_ID = "zenodo-doi-badge"

# Chapter notebooks open with front matter, title, author list, optional
# author notes, then the DOI badge. Checked in order; the first cell found
# is the one to follow.
BADGE_ANCHOR_IDS = (AUTHOR_NOTES_CELL_ID, AUTHOR_CELL_ID)

# Matches the container-title in deployed notebook citation YAML. Fixed here
# rather than read from config.yaml because build_citation_yaml_block only
# receives doi/book_doi.
CONTAINER_TITLE = "EarthRISE Applied Artificial Intelligence and Deep Learning Book"


def abbreviate_author(name: str) -> str:
    """'Bhandari, Biplov' -> 'Bhandari, B.'; 'dela Torre, Daniel Marc' -> 'dela Torre, D. M.'"""
    if ", " not in name:
        return name
    last, firsts = name.split(", ", 1)
    initials = [part.rstrip(".")[0] + "." for part in firsts.split()]
    return last + ", " + " ".join(initials)


def format_author_list(authors: list[dict]) -> str:
    """APA style: 'A, B.' for 1 author, 'A, B., & C, D.' for 2,
    'A, B., C, D., & E, F.' for 3 or more."""
    abbrevs = [abbreviate_author(a["name"]) for a in authors]
    if not abbrevs:
        # config.yaml allows an empty authors list for chapters awaiting their
        # roster; run() skips such chapters before any DOI exists, so this
        # only guards against calling the formatter directly.
        return ""
    if len(abbrevs) == 1:
        return abbrevs[0]
    if len(abbrevs) == 2:
        return f"{abbrevs[0]}, & {abbrevs[1]}"
    return ", ".join(abbrevs[:-1]) + ", & " + abbrevs[-1]


def build_citation_text(authors: list[dict], year: int, title: str, doi: str) -> str:
    author_str = format_author_list(authors)
    return (
        f"{author_str} ({year}). {title}. Zenodo. "
        f"[https://doi.org/{doi}](https://doi.org/{doi})"
    )


def build_badge_svg_md(doi: str) -> str:
    return f"[![DOI](https://zenodo.org/badge/DOI/{doi}.svg)](https://doi.org/{doi})"


def build_citation_yaml_block(doi: str, book_doi: str) -> str:
    return (
        f"{SENTINEL}\n"
        f"citation:\n"
        f"  type: book-chapter\n"
        f'  doi: "{doi}"\n'
        f'  url: "https://doi.org/{doi}"\n'
        f'  container-title: "{CONTAINER_TITLE}"\n'
        f'  container-doi: "{book_doi}"\n'
    )


def to_jupyter_lines(text: str) -> list[str]:
    """Split cell text the way Jupyter stores it: one string per line, newlines kept."""
    # A single joined string is valid JSON but differs from what Jupyter saves,
    # so git would show the whole cell as rewritten.
    return text.splitlines(keepends=True)


def build_badge_cell(ch: dict, ch_doi: str, book: dict, book_doi: str) -> dict:
    ch_cite = build_citation_text(ch["authors"], book["year"], ch["title"], ch_doi)
    ch_badge = build_badge_svg_md(ch_doi)
    book_cite = build_citation_text(book["authors"], book["year"], book["title"], book_doi)
    book_badge = build_badge_svg_md(book_doi)

    # The PDF block has no badges: Zenodo's SVG badges do not render in the
    # LaTeX PDF, and the DOI link carries the same information.
    body = (
        '::: {.content-visible when-format="html"}\n'
        "::: {.callout-note appearance='minimal'}\n"
        "**How to cite this chapter:**\n"
        "\n"
        f"{ch_cite} {ch_badge}\n"
        "\n"
        f"**Part of:** {book_cite} {book_badge}\n"
        ":::\n"
        "\n"
        ":::\n"
        "\n"
        '::: {.content-visible when-format="pdf"}\n'
        f"**How to cite this chapter:** {ch_cite}\n"
        "\n"
        f"**Part of:** {book_cite}\n"
        ":::\n"
    )
    return {
        "cell_type": "markdown",
        "id": BADGE_CELL_ID,
        "metadata": {},
        "source": to_jupyter_lines(body),
    }


def badge_insert_index(cells: list[dict]) -> int | None:
    """Index right after the author block, or None if the notebook has no author list."""
    ids = [cell.get("id") for cell in cells]
    for anchor in BADGE_ANCHOR_IDS:
        if anchor in ids:
            return ids.index(anchor) + 1
    return None


def strip_citation_block(front_matter: str) -> str:
    """Remove the citation block this script added earlier, marked by SENTINEL."""
    kept, in_block = [], False
    for line in front_matter.split("\n"):
        if line == SENTINEL:
            in_block = True
            continue
        if in_block and (line == "citation:" or line.startswith("  ")):
            continue
        in_block = False
        kept.append(line)
    return "\n".join(kept)


def add_citation_block(front_matter: str, doi: str, book_doi: str) -> str:
    """Insert the citation block just before the closing '---'."""
    yaml_block = build_citation_yaml_block(doi, book_doi)
    closing = re.search(r"\n---\s*$", front_matter)
    if closing:
        return front_matter[: closing.start()] + "\n" + yaml_block + "---"
    return front_matter.rstrip() + "\n" + yaml_block + "---"


def inject_notebook(
    nb_path: Path, ch: dict, doi: str, book_doi: str, book: dict, dry_run: bool
) -> bool:
    """Add or update the citation YAML and badge cell; True if the notebook changes."""
    if not nb_path.exists():
        print(f"  WARNING: not found: {nb_path}")
        return False

    try:
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        cells = nb["cells"]
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"  WARNING: could not parse {nb_path.name}: {exc}")
        return False

    raw_idx = next(
        (i for i, cell in enumerate(cells) if cell.get("cell_type") == "raw"), None
    )

    if raw_idx is None:
        # Chapters with no raw front-matter cell get a minimal Quarto
        # template; authors can extend it later.
        cells.insert(
            0,
            {
                "cell_type": "raw",
                "id": "quarto-yaml-front-matter",
                "metadata": {},
                "source": to_jupyter_lines("---\nformat:\n  html:\n    code-fold: true\n---"),
            },
        )
        raw_idx = 0

    raw_src = "".join(cells[raw_idx].get("source", []))
    base_src = strip_citation_block(raw_src)
    if re.search(r"^citation:", base_src, flags=re.MULTILINE):
        # A second `citation:` key would make the front matter invalid YAML.
        print(
            f"  SKIP (front matter has its own 'citation:' key): {nb_path.name}\n"
            "    Remove it, then rerun; inject.py manages the citation block."
        )
        return False
    new_src = add_citation_block(base_src, doi, book_doi)
    old_doi = re.search(r'^  doi: "([^"]+)"', raw_src, flags=re.MULTILINE)

    badge = build_badge_cell(ch, doi, book, book_doi)
    # Looked up after the front-matter cell may have been inserted, so the
    # indexes account for it.
    badge_idx = next((i for i, cell in enumerate(cells) if cell.get("id") == BADGE_CELL_ID), None)
    if badge_idx is not None:
        if new_src == raw_src and cells[badge_idx].get("source") == badge["source"]:
            print(f"  SKIP (up to date): {nb_path.name}")
            return False
        # Updated in place so the badge keeps its position and cell metadata.
        cells[badge_idx]["source"] = badge["source"]
        action = f"DOI {old_doi.group(1) if old_doi else '?'} -> {doi}, badge updated in place"
    else:
        badge_idx = badge_insert_index(cells)
        if badge_idx is None:
            print(
                f"  SKIP (no '{AUTHOR_CELL_ID}' cell): {nb_path.name}\n"
                "    Add the author cell after the chapter title (README: Prepare the notebook), then rerun."
            )
            return False
        cells.insert(badge_idx, badge)
        action = f"DOI {doi}, badge after cell '{cells[badge_idx - 1].get('id')}'"
    cells[raw_idx]["source"] = to_jupyter_lines(new_src)

    if dry_run:
        print(f"  [dry-run] would update {nb_path.name} ({action})")
        return True

    nb_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  UPDATED: {nb_path.name} ({action})")
    return True


def build_chapter_table_row(ch: dict, doi: str) -> str:
    num = ch["id"].removeprefix("ch")
    authors = format_author_list(ch["authors"])
    return f"| {num} | {ch['title']} | {authors} | [{doi}](https://doi.org/{doi}) |"


def update_citing_qmd(path: Path, config: dict, summary: dict, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("| # |")), None
    )
    if header_idx is None:
        print("  WARNING: chapter table not found in citing.qmd")
        return False

    sep_idx = header_idx + 1
    table_end = sep_idx + 1
    while table_end < len(lines) and lines[table_end].strip().startswith("|"):
        table_end += 1

    new_rows = [
        build_chapter_table_row(ch, summary["chapters"][ch["id"]]["concept_doi"])
        for ch in sorted(config["chapters"], key=chapter_sort_key)
        if ch["id"] in summary["chapters"]
    ]

    new_text = "\n".join(lines[: sep_idx + 1] + new_rows + lines[table_end:])

    if new_text == text:
        print("  citing.qmd: no changes needed")
        return False

    if dry_run:
        print(f"  [dry-run] would update citing.qmd ({len(new_rows)} chapter rows)")
        return True

    path.write_text(new_text, encoding="utf-8")
    print(f"  UPDATED: citing.qmd ({len(new_rows)} chapter rows)")
    return True


def run(args: argparse.Namespace) -> None:
    config = load_config()
    path = summary_path(args.sandbox)
    summary = load_summary(path)
    print(f"Summary: {path.name}")

    if not summary.get("chapters"):
        sys.exit(f"ERROR: no chapters in {path.name}. Run create.py first.")

    # The book cites concept DOIs, which always open the latest version.
    book_doi = (summary.get("book") or {}).get("concept_doi")
    if not book_doi:
        sys.exit(f"ERROR: book concept_doi not in {path.name}")
    chapters = filter_chapters(config["chapters"], args.chapter)

    changed = []
    for ch in chapters:
        if ch["id"] not in summary["chapters"]:
            print(f"  SKIP {ch['id']}: no DOI in {path.name} (run create.py first)")
            continue
        doi = summary["chapters"][ch["id"]]["concept_doi"]
        nb_path = REPO_DIR / ch["notebook"]
        if inject_notebook(nb_path, ch, doi, book_doi, config["book"], args.dry_run):
            changed.append(ch["id"])

    citing_path = REPO_DIR / "citing.qmd"
    if args.sandbox:
        # The table is rebuilt from the summary, and the sandbox summary lists
        # only rehearsed chapters, so it would drop every other row.
        print("  citing.qmd: skipped for sandbox runs")
    elif citing_path.exists():
        update_citing_qmd(citing_path, config, summary, args.dry_run)

    if args.dry_run:
        print(f"\nDry run complete. {len(changed)} notebook(s) would be modified.")
    else:
        print(f"\nInjection complete. {len(changed)} notebook(s) modified.")
        print("Next: review changes with 'git diff', then commit and push.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inject Zenodo DOI badges into chapter notebooks and citing.qmd."
    )
    parser.add_argument(
        "--chapter", metavar="ID", help="Only process this chapter id, e.g. ch10.2"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing files"
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Read DOIs from zenodo_summary.sandbox.json (sandbox rehearsal); citing.qmd is left alone",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
