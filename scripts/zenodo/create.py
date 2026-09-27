"""Create Zenodo chapter records and submit them to the community for review."""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

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

# Zenodo answers plain application/json on record endpoints with its legacy
# JSON shape; this media type returns the native InvenioRDM shape.
NATIVE_JSON = "application/vnd.inveniordm.v1+json"

RESOURCE_TYPE = "publication-section"
# Same publisher as the chapters deposited in June 2026.
PUBLISHER = "Zenodo"
REVIEW_MESSAGE = "Book chapter submitted by the EarthRISE book Zenodo pipeline."


class ZenodoClient:
    """Wraps the Zenodo InvenioRDM API. Holds host, token, and dry-run
    state as instance attributes so each method call stays clean."""

    def __init__(self, token: str, sandbox: bool = False, dry_run: bool = False):
        self.host = "sandbox.zenodo.org" if sandbox else "zenodo.org"
        self.base_url = f"https://{self.host}/api"
        self.token = token
        self.dry_run = dry_run

    def _headers(
        self, content_type: str | None = "application/json", accept: str = NATIVE_JSON
    ) -> dict:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": accept}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _draft_url(self, record_id: str, path: str = "") -> str:
        return f"{self.base_url}/records/{record_id}/draft{path}"

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
        try:
            # Kept long because InvenioRDM lists every invalid field under "errors".
            detail = json.dumps(resp.json(), indent=2)[:3000]
        except ValueError:
            detail = resp.text[:500]
        raise SystemExit(f"Zenodo API error [{action}] HTTP {resp.status_code}: {detail}")

    def get_community_id(self, slug: str) -> str:
        if self.dry_run:
            print(f"  [dry-run] would look up community '{slug}' on {self.host}")
            return "DRY_COMMUNITY"
        resp = self._request(
            "GET",
            f"{self.base_url}/communities/{quote(slug, safe='')}",
            headers=self._headers(content_type=None, accept="application/json"),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            raise SystemExit(
                f"ERROR: community '{slug}' not found on {self.host}.\n"
                "  Create it there, or fix book.community in config.yaml."
            )
        self._check(resp, f"get_community({slug})")
        return resp.json()["id"]

    def create_draft(self, payload: dict) -> dict:
        if self.dry_run:
            print("  [dry-run] would create draft with payload:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return {"id": "DRY"}
        resp = self._request(
            "POST",
            f"{self.base_url}/records",
            json=payload,
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, "create_draft")
        draft = resp.json()
        # Printed before any later step can fail, so an orphan draft is easy to find.
        html = draft.get("links", {}).get("self_html") or f"https://{self.host}/uploads/{draft['id']}"
        print(f"  Created draft {draft['id']}: {html}")
        return draft

    def reserve_doi(self, record_id: str) -> str:
        if self.dry_run:
            print("  [dry-run] would reserve DOI")
            return "10.5281/zenodo.DRY"
        resp = self._request(
            "POST",
            self._draft_url(record_id, "/pids/doi"),
            headers=self._headers(content_type=None),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"reserve_doi({record_id})")
        doi = resp.json()["pids"]["doi"]["identifier"]
        print(f"  Reserved DOI {doi}")
        return doi

    def upload_file(
        self, record_id: str, file_path: Path, upload_name: str | None = None
    ) -> None:
        if not file_path.exists():
            print(f"  WARNING: not found, skipping: {file_path}")
            return
        key = upload_name or file_path.name
        size = file_path.stat().st_size
        if self.dry_run:
            print(f"  [dry-run] upload {key} ({size:,} bytes)")
            return

        resp = self._request(
            "POST",
            self._draft_url(record_id, "/files"),
            json=[{"key": key}],
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"init_upload({key})")

        # The book-prefixed PDF name contains spaces, so the key must be encoded.
        file_url = self._draft_url(record_id, f"/files/{quote(key, safe='')}")
        with file_path.open("rb") as f:
            resp = self._request(
                "PUT",
                f"{file_url}/content",
                data=f,
                headers=self._headers(content_type="application/octet-stream"),
                timeout=UPLOAD_TIMEOUT,
            )
        self._check(resp, f"upload_content({key})")

        resp = self._request(
            "POST",
            f"{file_url}/commit",
            headers=self._headers(content_type=None),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"commit_upload({key})")
        print(f"  Uploaded {key} ({size:,} bytes)")

    def create_review_request(self, record_id: str, community_id: str) -> None:
        if self.dry_run:
            print("  [dry-run] would link the draft to the community for review")
            return
        resp = self._request(
            "PUT",
            self._draft_url(record_id, "/review"),
            json={"receiver": {"community": community_id}, "type": "community-submission"},
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"create_review({record_id})")

    def submit_review(self, record_id: str) -> str:
        """Submit the draft for review and return the request's web URL."""
        if self.dry_run:
            print("  [dry-run] would submit for community review (require_review: true)")
            return ""
        resp = self._request(
            "POST",
            self._draft_url(record_id, "/actions/submit-review"),
            json={
                "payload": {"content": REVIEW_MESSAGE, "format": "html"},
                # Without this, Zenodo publishes immediately when the submitter
                # may add records to the community directly (e.g. a manager).
                "require_review": True,
            },
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"submit_review({record_id})")
        request = resp.json()
        status = request.get("status")
        if status == "submitted":
            print("  Submitted for community review")
        else:
            print(
                f"  WARNING: review request status is '{status}', not 'submitted'.\n"
                f"  The record may already be published; check it on {self.host}."
            )
        return request.get("links", {}).get("self_html") or f"https://{self.host}/me/requests"


def parse_author_name(name: str) -> tuple[str, str]:
    """'dela Torre, Daniel Marc' -> ('dela Torre', 'Daniel Marc')."""
    family, sep, given = name.partition(", ")
    if not sep or not family.strip() or not given.strip():
        raise ValueError(f"author name must be 'Last, First': {name!r}")
    return family.strip(), given.strip()


def parse_affiliations(author: dict) -> list[str]:
    """Return the author's `affiliations` list, one item per organization."""
    name = author.get("name", "?")
    # Rejected rather than tolerated: an old-format entry would silently lose
    # its affiliations, and a bare string would be sent letter by letter.
    if "affiliation" in author:
        raise ValueError(
            f"{name}: 'affiliation' is the old string format; use an 'affiliations' list "
            "with one item per organization"
        )
    affiliations = author.get("affiliations", [])
    if not isinstance(affiliations, list) or not all(
        isinstance(item, str) and item.strip() for item in affiliations
    ):
        raise ValueError(f"{name}: 'affiliations' must be a list of non-empty names")
    return [item.strip() for item in affiliations]


def to_rdm_creators(authors: list[dict]) -> list[dict]:
    """Config author dicts to InvenioRDM creators. Drops an empty ORCID or
    affiliation list rather than sending blank values."""
    creators = []
    for author in authors:
        family, given = parse_author_name(author["name"])
        person = {
            "type": "personal",
            "name": author["name"],
            "family_name": family,
            "given_name": given,
        }
        if author.get("orcid"):
            person["identifiers"] = [{"scheme": "orcid", "identifier": author["orcid"]}]
        creator = {"person_or_org": person}
        affiliations = parse_affiliations(author)
        if affiliations:
            creator["affiliations"] = [{"name": affiliation} for affiliation in affiliations]
        creators.append(creator)
    return creators


def _related(identifier: str, scheme: str, relation: str, resource_type: str) -> dict:
    return {
        "identifier": identifier,
        "scheme": scheme,
        "relation_type": {"id": relation},
        "resource_type": {"id": resource_type},
    }


def build_chapter_payload(
    ch: dict,
    book_doi: str,
    book_config: dict,
    version: str = "v1",
    publication_date: str | None = None,
) -> dict:
    """Build the InvenioRDM draft payload for one chapter record."""
    # .as_posix() keeps the GitHub URL correct on Windows, where Path str()
    # would otherwise emit backslashes.
    github_path = Path(ch["notebook"]).parent.parent.as_posix()
    github_url = f"{book_config['github_url']}/tree/main/{github_path}"

    related_identifiers = [
        _related(book_doi, "doi", "ispartof", "publication-book"),
        _related(github_url, "url", "issupplementedby", "software"),
    ]
    if ch.get("youtube_url"):
        related_identifiers.append(
            _related(ch["youtube_url"], "url", "issupplementedby", "video")
        )

    return {
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": True},
        "metadata": {
            "resource_type": {"id": RESOURCE_TYPE},
            "title": ch["title"].strip(),
            "publication_date": publication_date or date.today().isoformat(),
            "publisher": PUBLISHER,
            "version": version,
            "description": ch["description"].strip(),
            "creators": to_rdm_creators(ch["authors"]),
            "subjects": [{"subject": keyword} for keyword in ch.get("keywords", [])],
            "rights": [{"id": book_config["license"]}],
            "languages": [{"id": book_config["language"]}],
            "related_identifiers": related_identifiers,
        },
    }


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
    community = config["book"].get("community", "")
    if not community:
        sys.exit("ERROR: book.community is not set in config.yaml")
    print(f"Mode: {mode}  |  Community: {community}")

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

    # Validated up front, before any draft is created, so a bad config
    # entry never leaves a run half-completed.
    for ch in new_chapters:
        if not ch.get("authors"):
            sys.exit(f"ERROR: {ch['id']} has empty authors in config.yaml")
        try:
            to_rdm_creators(ch["authors"])
        except ValueError as exc:
            sys.exit(f"ERROR: {ch['id']} in config.yaml: {exc}")

    for ch in new_chapters:
        pdf = find_chapter_pdf(ch, REPO_DIR, pdf_dir)
        if not pdf and not args.dry_run:
            sys.exit(
                f"ERROR: PDF not found for {ch['id']}.\n"
                f"  Render it first: python scripts/zenodo/render_pdf.py {ch['id']}"
            )

    community_id = client.get_community_id(community)

    submitted = []
    for ch in new_chapters:
        print(f"\n  {ch['id']}: {ch['title'][:60]}")
        draft = client.create_draft(build_chapter_payload(ch, book_doi, config["book"]))
        record_id = draft["id"]
        doi = client.reserve_doi(record_id)

        pdf = find_chapter_pdf(ch, REPO_DIR, pdf_dir)
        if pdf:
            client.upload_file(record_id, pdf, upload_name=pdf_upload_name(ch, config["book"]))
        for notebook in find_chapter_notebooks(ch, REPO_DIR):
            client.upload_file(record_id, notebook)

        client.create_review_request(record_id, community_id)
        review_url = client.submit_review(record_id)

        if args.dry_run:
            print(f"  [dry-run] would record {ch['id']} -> record {record_id}, DOI {doi}")
            continue

        # Saved after each chapter, not once at the end, so a mid-run
        # failure still leaves completed chapters recorded and a rerun
        # skips them instead of creating duplicate records.
        summary.setdefault("chapters", {})[ch["id"]] = {
            "deposit_id": int(record_id),
            "doi": doi,
        }
        save_summary(summary)
        submitted.append((ch["id"], review_url))

    print(f"\nDone. {len(new_chapters)} chapter(s) processed.")
    if submitted:
        print("Accept each review request to publish the record into the community:")
        for chapter_id, url in submitted:
            print(f"  {chapter_id}: {url}")
        print("Run inject.py only after the records are published.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Zenodo chapter records and submit them to the community for review."
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
        "--pdf-dir", metavar="PATH", help="Override PDF directory (default: looks in _book/)"
    )
    parser.add_argument(
        "--skip-preflight", action="store_true", help="Skip the file and author preflight check"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
