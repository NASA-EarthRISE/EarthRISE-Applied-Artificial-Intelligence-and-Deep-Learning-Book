"""Client for Zenodo's InvenioRDM REST API."""

import json
from pathlib import Path
from urllib.parse import quote

import requests

REQUEST_TIMEOUT = 30
UPLOAD_TIMEOUT = 300

# Zenodo answers plain application/json on record endpoints with its legacy
# JSON shape; this media type returns the native InvenioRDM shape.
NATIVE_JSON = "application/vnd.inveniordm.v1+json"

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
            return {"id": "DRY", "parent": {"id": "DRY_PARENT"}}
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

    def new_version(self, record_id: int | str) -> dict:
        """Draft of the record's next version. If an earlier run left one, Zenodo returns it."""
        if self.dry_run:
            print(f"  [dry-run] would create a new version of record {record_id}")
            return {"id": "DRY", "versions": {"index": "N"}}
        resp = self._request(
            "POST",
            f"{self.base_url}/records/{record_id}/versions",
            headers=self._headers(content_type=None),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"new_version({record_id})")
        draft = resp.json()
        html = draft.get("links", {}).get("self_html") or f"https://{self.host}/uploads/{draft['id']}"
        print(f"  New version draft {draft['id']} (version {draft['versions']['index']}): {html}")
        return draft

    def update_draft(self, record_id: str, payload: dict) -> None:
        if self.dry_run:
            print("  [dry-run] would set draft metadata to:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        resp = self._request(
            "PUT",
            self._draft_url(record_id),
            json=payload,
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"update_draft({record_id})")

    def clear_draft_files(self, record_id: str) -> None:
        """Remove files an earlier run left on the draft, so uploads start clean."""
        if self.dry_run:
            return
        resp = self._request(
            "GET",
            self._draft_url(record_id, "/files"),
            headers=self._headers(content_type=None),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"list_files({record_id})")
        for entry in resp.json().get("entries", []):
            key = entry["key"]
            resp = self._request(
                "DELETE",
                self._draft_url(record_id, f"/files/{quote(key, safe='')}"),
                headers=self._headers(content_type=None),
                timeout=REQUEST_TIMEOUT,
            )
            self._check(resp, f"delete_file({key})")
            print(f"  Removed leftover file {key}")

    def get_review(self, record_id: str) -> dict | None:
        """The draft's review request, or None if it has none."""
        if self.dry_run:
            return None
        resp = self._request(
            "GET",
            self._draft_url(record_id, "/review"),
            headers=self._headers(content_type=None),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        self._check(resp, f"get_review({record_id})")
        return resp.json()

    def publish(self, record_id: str) -> dict:
        resp = self._request(
            "POST",
            self._draft_url(record_id, "/actions/publish"),
            headers=self._headers(content_type=None),
            timeout=REQUEST_TIMEOUT,
        )
        self._check(resp, f"publish({record_id})")
        record = resp.json()
        print(f"  Published record {record['id']}, DOI {record['pids']['doi']['identifier']}")
        return record
