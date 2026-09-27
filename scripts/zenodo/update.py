"""Publish new versions of the book and chapter records on Zenodo."""

import argparse
import os
import sys
from pathlib import Path

from common import (
    REPO_DIR,
    chapter_sort_key,
    filter_chapters,
    load_config,
    load_summary,
    save_summary,
    summary_path,
)
from create import (
    ZenodoClient,
    author_cell_problem,
    build_book_payload,
    build_chapter_payload,
    find_chapter_notebooks,
    find_chapter_pdf,
    pdf_upload_name,
    to_rdm_creators,
)


def book_pdf_path(book_config: dict) -> Path:
    # `quarto render --to pdf` names the book PDF after the book title in
    # _quarto.yml, which is the same name as pdf_prefix.
    return REPO_DIR / "_book" / f"{book_config['pdf_prefix']}.pdf"


def book_target(config: dict, summary: dict, dry_run: bool) -> dict:
    book = config["book"]
    entry = summary.get("book") or {}
    if not entry.get("deposit_id"):
        sys.exit("ERROR: no book record (deposit_id) in the summary file")
    try:
        to_rdm_creators(book["authors"])
    except ValueError as exc:
        sys.exit(f"ERROR: book.authors in config.yaml: {exc}")
    pdf = book_pdf_path(book)
    files = [(pdf, pdf.name)]
    if not pdf.exists():
        if not dry_run:
            sys.exit(f"ERROR: book PDF not found: {pdf}\n  Render it first: quarto render --to pdf")
        print(f"  [dry-run] book PDF not rendered yet: {pdf.name}")
        files = []
    chapter_dois = [
        summary["chapters"][ch["id"]]["concept_doi"]
        for ch in sorted(config["chapters"], key=chapter_sort_key)
        if ch["id"] in summary.get("chapters", {})
    ]
    return {
        "name": "book",
        "entry": entry,
        "files": files,
        "payload": lambda version: build_book_payload(book, chapter_dois, version),
    }


def chapter_target(ch: dict, config: dict, summary: dict, dry_run: bool) -> dict:
    entry = summary.get("chapters", {}).get(ch["id"])
    if not entry:
        sys.exit(f"ERROR: {ch['id']} has no record in the summary file; use create.py for new chapters")
    try:
        to_rdm_creators(ch["authors"])
    except ValueError as exc:
        sys.exit(f"ERROR: {ch['id']} in config.yaml: {exc}")
    problem = author_cell_problem(REPO_DIR / ch["notebook"])
    if problem:
        sys.exit(f"ERROR: {ch['id']}: {problem}")
    pdf = find_chapter_pdf(ch, REPO_DIR)
    if not pdf and not dry_run:
        sys.exit(f"ERROR: PDF not found for {ch['id']}.\n  Render it first: python render_pdf.py {ch['id']}")
    if not pdf:
        print(f"  [dry-run] {ch['id']} PDF not rendered yet")
    book_doi = summary["book"]["concept_doi"]
    return {
        "name": ch["id"],
        "entry": entry,
        "files": ([(pdf, pdf_upload_name(ch, config["book"]))] if pdf else [])
        + [(notebook, None) for notebook in find_chapter_notebooks(ch, REPO_DIR)],
        "payload": lambda version: build_chapter_payload(ch, book_doi, config["book"], version),
    }


def update_record(client: ZenodoClient, target: dict, dry_run: bool) -> bool:
    """Create the next version with new files and metadata; True if the summary entry changed."""
    print(f"\n  {target['name']}: new version of record {target['entry']['deposit_id']}")
    draft = client.new_version(target["entry"]["deposit_id"])
    version = f"v{draft['versions']['index']}"
    client.update_draft(draft["id"], target["payload"](version))
    # New versions start without files; every file is uploaded fresh.
    client.clear_draft_files(draft["id"])
    for path, key in target["files"]:
        client.upload_file(draft["id"], path, upload_name=key)

    if dry_run:
        print(f"  [dry-run] would ask to publish {version}")
        return False

    if client.get_review(draft["id"]):
        # Zenodo decides per community whether new versions need a review.
        review_url = client.submit_review(draft["id"])
        target["entry"]["deposit_id"] = int(draft["id"])
        print(f"  Accept the review to publish {version}: {review_url}")
        return True

    preview = f"https://{client.host}/records/{draft['id']}?preview=1"
    answer = input(f"  Check the draft at {preview}\n  Publish {version} of {target['name']}? [y/N] ")
    if answer.strip().lower() != "y":
        print("  Not published. The draft stays on Zenodo; rerun update.py to continue it.")
        return False
    record = client.publish(draft["id"])
    target["entry"]["deposit_id"] = int(record["id"])
    return True


def run(args: argparse.Namespace) -> None:
    config = load_config()
    path = summary_path(args.sandbox)
    summary = load_summary(path)

    mode = "DRY RUN" if args.dry_run else ("SANDBOX" if args.sandbox else "PRODUCTION")
    print(f"Mode: {mode}  |  Summary: {path.name}")

    token = os.environ.get("ZENODO_TOKEN", "")
    if not token and not args.dry_run:
        sys.exit("ERROR: set ZENODO_TOKEN environment variable")
    if not (summary.get("book") or {}).get("concept_doi"):
        sys.exit(f"ERROR: book concept_doi not in {path.name}")

    # All targets are validated before any version is created.
    if args.book:
        targets = [book_target(config, summary, args.dry_run)]
    else:
        targets = [
            chapter_target(ch, config, summary, args.dry_run)
            for ch in filter_chapters(config["chapters"], args.chapter)
        ]

    client = ZenodoClient(token, sandbox=args.sandbox, dry_run=args.dry_run)
    for target in targets:
        if update_record(client, target, args.dry_run):
            # Saved per record, so a later failure keeps earlier results.
            save_summary(summary, path)

    print("\nDone.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--chapter", metavar="ID", help="Only this chapter, e.g. ch10.2 (default: all chapters)")
    target.add_argument("--book", action="store_true", help="The book record instead of chapters")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without calling Zenodo")
    parser.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org and zenodo_summary.sandbox.json")
    return parser.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
