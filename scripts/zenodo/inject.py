"""Inject Zenodo DOI badges into chapter notebooks and update citing.qmd."""

import argparse
import json
import re
import sys
from pathlib import Path

from common import (
    REPO_DIR,
    chapter_sort_key,
    filter_chapters,
    load_config,
    load_summary,
)

SENTINEL = "# zenodo-doi-injected"
BADGE_CELL_ID = "zenodo-doi-badge"

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


def build_badge_cell(ch: dict, ch_doi: str, book: dict, book_doi: str) -> dict:
    ch_cite = build_citation_text(ch["authors"], book["year"], ch["title"], ch_doi)
    ch_badge = build_badge_svg_md(ch_doi)
    book_cite = build_citation_text(book["authors"], book["year"], book["title"], book_doi)
    book_badge = build_badge_svg_md(book_doi)

    # A single joined string, matching the one-element source list format
    # used in existing badge cells.
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
    )
    return {
        "cell_type": "markdown",
        "id": BADGE_CELL_ID,
        "metadata": {},
        "source": [body],
    }


def inject_notebook(
    nb_path: Path, ch: dict, doi: str, book_doi: str, book: dict, dry_run: bool
) -> bool:
    if not nb_path.exists():
        print(f"  WARNING: not found: {nb_path}")
        return False

    try:
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        cells = nb["cells"]
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"  WARNING: could not parse {nb_path.name}: {exc}")
        return False

    for cell in cells:
        if cell.get("id") == BADGE_CELL_ID:
            print(f"  SKIP (already injected): {nb_path.name}")
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
                "source": ["---\nformat:\n  html:\n    code-fold: true\n---"],
            },
        )
        raw_idx = 0

    raw_src = "".join(cells[raw_idx].get("source", []))

    if SENTINEL in raw_src:
        print(f"  SKIP (sentinel found): {nb_path.name}")
        return False

    yaml_block = build_citation_yaml_block(doi, book_doi)
    closing = re.search(r"\n---\s*$", raw_src)
    if closing:
        new_src = raw_src[: closing.start()] + "\n" + yaml_block + "---"
    else:
        new_src = raw_src.rstrip() + "\n" + yaml_block + "---"

    cells[raw_idx]["source"] = [new_src]
    cells.insert(raw_idx + 1, build_badge_cell(ch, doi, book, book_doi))

    if dry_run:
        print(f"  [dry-run] would inject DOI {doi} into {nb_path.name}")
        return True

    nb_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  INJECTED: {nb_path.name} (DOI: {doi})")
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
        build_chapter_table_row(ch, summary["chapters"][ch["id"]]["doi"])
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
    summary = load_summary()

    if not summary.get("chapters"):
        sys.exit("ERROR: no chapters in zenodo_summary.json. Run create.py first.")

    book_doi = summary.get("book", {}).get("doi", "")
    if not book_doi:
        sys.exit("ERROR: book DOI not in zenodo_summary.json")
    chapters = filter_chapters(config["chapters"], args.chapter)

    changed = []
    for ch in chapters:
        if ch["id"] not in summary["chapters"]:
            print(f"  SKIP {ch['id']}: no DOI in summary (run create.py first)")
            continue
        doi = summary["chapters"][ch["id"]]["doi"]
        nb_path = REPO_DIR / ch["notebook"]
        if inject_notebook(nb_path, ch, doi, book_doi, config["book"], args.dry_run):
            changed.append(ch["id"])

    citing_path = REPO_DIR / "citing.qmd"
    if citing_path.exists():
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
    return parser.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
