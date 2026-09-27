"""Create Zenodo chapter records in two steps and submit them for community review."""

import argparse
import os
import sys
from pathlib import Path

from common import (
    DRAFT_STATUS,
    REPO_DIR,
    author_cell_problem,
    filter_chapters,
    find_chapter_notebooks,
    find_chapter_pdf,
    load_config,
    load_summary,
    pdf_upload_name,
    preflight,
    save_summary,
    summary_path,
)
from metadata import build_chapter_payload, concept_doi_for, to_rdm_creators
from zenodo_api import ZenodoClient


def validate_chapter(ch: dict) -> None:
    """Stop before any API call if the chapter's config or notebook is not ready."""
    if not ch.get("authors"):
        sys.exit(f"ERROR: {ch['id']} has empty authors in config.yaml")
    try:
        to_rdm_creators(ch["authors"])
    except ValueError as exc:
        sys.exit(f"ERROR: {ch['id']} in config.yaml: {exc}")
    problem = author_cell_problem(REPO_DIR / ch["notebook"])
    if problem:
        sys.exit(
            f"ERROR: {ch['id']}: {problem}.\n"
            "  Add the author cell (README: Prepare the notebook), then rerun."
        )


def start_chapters(client, chapters, config, summary, path, args, book_doi) -> None:
    """Step 1: create each draft and reserve its DOI, so the DOI can go into the PDF."""
    existing = summary.get("chapters", {})
    new_chapters = []
    for ch in chapters:
        if ch["id"] in existing:
            print(f"  {ch['id']}: already in {path.name}, skipping")
        else:
            new_chapters.append(ch)
    if not new_chapters:
        print("No new chapters to start.")
        return

    for ch in new_chapters:
        validate_chapter(ch)
    # Checked now so a missing community fails before any draft exists.
    client.get_community_id(config["book"]["community"])

    for ch in new_chapters:
        print(f"\n  {ch['id']}: {ch['title'][:60]}")
        draft = client.create_draft(build_chapter_payload(ch, book_doi, config["book"]))
        concept_doi = concept_doi_for(draft, client.reserve_doi(draft["id"]))
        if args.dry_run:
            print(f"  [dry-run] would record {ch['id']} as a draft, concept DOI {concept_doi}")
            continue
        # Saved per chapter, so a rerun skips chapters that already have a draft.
        summary.setdefault("chapters", {})[ch["id"]] = {
            "deposit_id": int(draft["id"]),
            "concept_doi": concept_doi,
            "status": DRAFT_STATUS,
        }
        save_summary(summary, path)
        print(f"  Recorded in {path.name}; concept DOI {concept_doi}")

    sandbox = " --sandbox" if args.sandbox else ""
    print("\nNext, for each chapter:")
    print(f"  python inject.py --chapter <ID>{sandbox}")
    print("  python render_pdf.py <ID>")
    print(f"  python create.py --chapter <ID> --submit{sandbox}")


def submit_chapters(client, chapters, config, summary, path, args, book_doi) -> None:
    """Step 2: refresh metadata, upload the rendered PDF and notebook, submit for review."""
    pdf_dir = Path(args.pdf_dir).expanduser() if args.pdf_dir else None
    existing = summary.get("chapters", {})
    drafts = []
    for ch in chapters:
        if existing.get(ch["id"], {}).get("status") == DRAFT_STATUS:
            drafts.append(ch)
        elif args.chapter:
            print(f"  {ch['id']}: not a draft waiting for --submit (run create.py without --submit first)")
    if not drafts:
        print("No drafts waiting for --submit.")
        return

    if not args.skip_preflight:
        preflight(config, pdf_dir, args.chapter)
    for ch in drafts:
        validate_chapter(ch)
        if not find_chapter_pdf(ch, REPO_DIR, pdf_dir) and not args.dry_run:
            sys.exit(f"ERROR: PDF not found for {ch['id']}.\n  Render it first: python render_pdf.py {ch['id']}")
    community_id = client.get_community_id(config["book"]["community"])

    submitted = []
    for ch in drafts:
        entry = existing[ch["id"]]
        record_id = str(entry["deposit_id"])
        print(f"\n  {ch['id']}: draft {record_id}")
        # Refreshed so config edits made since step 1 are included.
        client.update_draft(record_id, build_chapter_payload(ch, book_doi, config["book"]))
        # A rerun after a failed upload starts from a clean file list.
        client.clear_draft_files(record_id)
        pdf = find_chapter_pdf(ch, REPO_DIR, pdf_dir)
        if pdf:
            client.upload_file(record_id, pdf, upload_name=pdf_upload_name(ch, config["book"]))
        for notebook in find_chapter_notebooks(ch, REPO_DIR):
            client.upload_file(record_id, notebook)
        client.create_review_request(record_id, community_id)
        review_url = client.submit_review(record_id)
        if args.dry_run:
            continue
        # From here on the entry looks like any other chapter's.
        del entry["status"]
        save_summary(summary, path)
        submitted.append((ch["id"], review_url))

    if submitted:
        print("\nAccept each review request to publish the chapter:")
        for chapter_id, url in submitted:
            print(f"  {chapter_id}: {url}")
        print("Then re-render the book and run update.py --book, so the book lists the new chapter.")


def run(args: argparse.Namespace) -> None:
    config = load_config()
    path = summary_path(args.sandbox)
    summary = load_summary(path)

    mode = "DRY RUN" if args.dry_run else ("SANDBOX" if args.sandbox else "PRODUCTION")
    step = "submit" if args.submit else "start"
    if not config["book"].get("community"):
        sys.exit("ERROR: book.community is not set in config.yaml")
    print(f"Mode: {mode}  |  Step: {step}  |  Summary: {path.name}")

    token = os.environ.get("ZENODO_TOKEN", "")
    if not token and not args.dry_run:
        sys.exit("ERROR: set ZENODO_TOKEN environment variable")

    # Chapters link to the book's concept DOI, which always opens its latest version.
    book_doi = (summary.get("book") or {}).get("concept_doi")
    if not book_doi:
        sys.exit(f"ERROR: book concept_doi not in {path.name}")

    client = ZenodoClient(token, sandbox=args.sandbox, dry_run=args.dry_run)
    chapters = filter_chapters(config["chapters"], args.chapter)
    step_fn = submit_chapters if args.submit else start_chapters
    step_fn(client, chapters, config, summary, path, args, book_doi)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create Zenodo chapter records in two steps: create the draft and reserve its DOI, "
            "then (--submit) upload the rendered PDF and submit for community review."
        )
    )
    parser.add_argument(
        "--chapter", metavar="ID", help="Only process this chapter id, e.g. ch11.1"
    )
    parser.add_argument(
        "--submit", action="store_true",
        help="Step 2: upload the PDF and notebook and submit the draft for review",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate without calling the Zenodo API"
    )
    parser.add_argument(
        "--sandbox", action="store_true", help="Use sandbox.zenodo.org and zenodo_summary.sandbox.json"
    )
    parser.add_argument(
        "--pdf-dir", metavar="PATH", help="Override PDF directory (default: looks in _book/)"
    )
    parser.add_argument(
        "--skip-preflight", action="store_true", help="Skip the file and author preflight check"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
