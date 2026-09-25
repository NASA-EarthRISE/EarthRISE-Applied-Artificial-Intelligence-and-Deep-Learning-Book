"""Create Zenodo deposits for book chapters and record their DOIs."""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

from common import (
    REPO_DIR,
    filter_chapters,
    load_config,
    load_summary,
    save_summary,
)

REQUEST_TIMEOUT = 30
UPLOAD_TIMEOUT = 300


class ZenodoClient:
    """Wraps the Zenodo deposit API. Holds base URL, token, and dry-run
    state as instance attributes so each method call stays clean."""

    def __init__(self, token: str, sandbox: bool = False, dry_run: bool = False):
        self.base_url = (
            "https://sandbox.zenodo.org/api" if sandbox else "https://zenodo.org/api"
        )
        self.token = token
        self.dry_run = dry_run

    def _headers(self, content_type: str = "application/json") -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _request(self, method: str, url: str, *, timeout: int, **kwargs) -> requests.Response:
        # Centralized here so every call gets a bounded timeout and a clean
        # error instead of a raw traceback on DNS/connection failures.
        try:
            return requests.request(method, url, timeout=timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise SystemExit(f"Zenodo request failed [{method} {url}]: {exc}") from exc

    def _check(self, resp: requests.Response, action: str) -> None:
        if resp.ok:
            return
        detail = resp.text[:300]
        try:
            # resp.json() raises a ValueError subclass on a non-JSON body.
            detail = json.dumps(resp.json(), indent=2)[:300]
        except ValueError:
            pass
        raise SystemExit(f"Zenodo API error [{action}] HTTP {resp.status_code}: {detail}")

    def create_deposit(self) -> dict:
        if self.dry_run:
            print("  [dry-run] would create deposit")
            return {
                "id": "DRY",
                "links": {"bucket": "DRY_BUCKET"},
                "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.DRY"}},
            }
        resp = self._request(
            "POST",
            f"{self.base_url}/deposit/depositions",
            json={},
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, "create_deposit")
        deposit = resp.json()
        doi = deposit["metadata"]["prereserve_doi"]["doi"]
        print(f"  Created deposit {deposit['id']}, DOI: {doi}")
        return deposit

    def update_metadata(self, deposit_id: int | str, metadata: dict) -> None:
        if self.dry_run:
            print(f"  [dry-run] metadata: {metadata.get('title', '')[:60]}")
            return
        resp = self._request(
            "PUT",
            f"{self.base_url}/deposit/depositions/{deposit_id}",
            data=json.dumps({"metadata": metadata}),
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"update_metadata({deposit_id})")

    def upload_file(self, deposit: dict, file_path: Path) -> None:
        if not file_path.exists():
            print(f"  WARNING: not found, skipping: {file_path}")
            return
        size = file_path.stat().st_size
        if self.dry_run:
            print(f"  [dry-run] upload {file_path.name} ({size:,} bytes)")
            return
        with file_path.open("rb") as f:
            resp = self._request(
                "PUT",
                f"{deposit['links']['bucket']}/{file_path.name}",
                data=f,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=UPLOAD_TIMEOUT,
            )
        self._check(resp, f"upload({file_path.name})")
        print(f"  Uploaded {file_path.name} ({size:,} bytes)")

    def publish(self, deposit_id: int | str) -> str:
        if self.dry_run:
            return f"10.5281/zenodo.{deposit_id}"
        resp = self._request(
            "POST",
            f"{self.base_url}/deposit/depositions/{deposit_id}/actions/publish",
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"publish({deposit_id})")
        doi = resp.json().get("doi", "")
        print(f"  Published deposit {deposit_id}, DOI: {doi}")
        return doi


def to_zenodo_creators(authors: list[dict]) -> list[dict]:
    """Config author dicts to Zenodo creator format. Drops empty orcid or
    affiliation rather than sending blank strings the API would still accept."""
    creators = []
    for author in authors:
        creator = {"name": author["name"]}
        if author.get("orcid"):
            creator["orcid"] = author["orcid"]
        if author.get("affiliation"):
            creator["affiliation"] = author["affiliation"]
        creators.append(creator)
    return creators


def build_chapter_metadata(ch: dict, book_doi: str, book_config: dict) -> dict:
    """Build the Zenodo metadata payload for one chapter deposit."""
    # .as_posix() keeps the GitHub URL correct on Windows, where Path str()
    # would otherwise emit backslashes.
    github_path = Path(ch["notebook"]).parent.parent.as_posix()
    github_url = f"{book_config['github_url']}/tree/main/{github_path}"

    return {
        "upload_type": "publication",
        "publication_type": "section",
        "title": ch["title"].strip(),
        "description": ch["description"].strip(),
        "creators": to_zenodo_creators(ch["authors"]),
        "keywords": ch.get("keywords", []),
        "license": book_config["license"],
        "access_right": "open",
        "language": book_config["language"],
        "prereserve_doi": True,
        "communities": [{"identifier": book_config["community"]}],
        "related_identifiers": [
            {
                "identifier": book_doi,
                "relation": "isPartOf",
                "resource_type": "publication-book",
            },
            {
                "identifier": github_url,
                "relation": "isSupplementedBy",
                "resource_type": "software",
            },
        ],
    }


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

        if not pdf and not notebooks:
            print("  WARNING: nothing to upload for this chapter")
            all_ok = False

    print()
    return all_ok


def run(args: argparse.Namespace) -> None:
    config = load_config()
    summary = load_summary()

    mode = "DRY RUN" if args.dry_run else ("SANDBOX" if args.sandbox else "PRODUCTION")
    print(f"Mode: {mode}  |  Publish: {args.publish}")

    token = os.environ.get("ZENODO_TOKEN", "")
    if not token and not args.dry_run:
        sys.exit("ERROR: set ZENODO_TOKEN environment variable")

    client = ZenodoClient(token, sandbox=args.sandbox, dry_run=args.dry_run)

    book_doi = summary.get("book", {}).get("doi", "")
    if not book_doi:
        sys.exit("ERROR: book DOI not in zenodo_summary.json")

    pdf_dir = Path(args.pdf_dir).expanduser() if args.pdf_dir else None
    chapters = filter_chapters(config["chapters"], args.chapter)
    existing = summary.get("chapters", {})

    new_chapters = []
    for ch in chapters:
        if ch["id"] in existing:
            print(f"  {ch['id']}: already has a deposit, skipping")
        else:
            new_chapters.append(ch)

    if not new_chapters:
        print("All specified chapters already have deposits.")
        return

    if not args.skip_preflight:
        preflight(config, pdf_dir, args.chapter)

    # Validated up front, before any deposit is created, so a bad config
    # entry never leaves a run half-completed.
    for ch in new_chapters:
        if not ch.get("authors"):
            sys.exit(f"ERROR: {ch['id']} has empty authors in config.yaml")

    for ch in new_chapters:
        pdf = find_chapter_pdf(ch, REPO_DIR, pdf_dir)
        if not pdf and not args.dry_run:
            sys.exit(
                f"ERROR: PDF not found for {ch['id']}.\n"
                f"  Render it first: python scripts/zenodo/render_pdf.py {ch['id']}"
            )

    for ch in new_chapters:
        print(f"\n  {ch['id']}: {ch['title'][:60]}")
        deposit = client.create_deposit()
        chapter_doi = deposit["metadata"]["prereserve_doi"]["doi"]

        metadata = build_chapter_metadata(ch, book_doi, config["book"])
        client.update_metadata(deposit["id"], metadata)

        pdf = find_chapter_pdf(ch, REPO_DIR, pdf_dir)
        if pdf:
            client.upload_file(deposit, pdf)

        for notebook in find_chapter_notebooks(ch, REPO_DIR):
            client.upload_file(deposit, notebook)

        if args.publish:
            chapter_doi = client.publish(deposit["id"])

        if args.dry_run:
            print(f"  [dry-run] would record {ch['id']} -> deposit {deposit['id']}")
            continue

        # Saved after each chapter, not once at the end, so a mid-run
        # failure still leaves completed chapters recorded and a rerun
        # skips them instead of creating duplicate deposits.
        summary.setdefault("chapters", {})[ch["id"]] = {
            "deposit_id": deposit["id"],
            "doi": chapter_doi,
        }
        save_summary(summary)

    print(f"\nDone. {len(new_chapters)} chapter(s) processed.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Zenodo deposits for book chapters."
    )
    parser.add_argument(
        "--chapter", metavar="ID", help="Only process this chapter id, e.g. ch10.2"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate without calling the Zenodo API"
    )
    parser.add_argument(
        "--sandbox", action="store_true", help="Use sandbox.zenodo.org instead of zenodo.org"
    )
    parser.add_argument(
        "--publish", action="store_true", help="Publish deposits instead of leaving them as drafts"
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
