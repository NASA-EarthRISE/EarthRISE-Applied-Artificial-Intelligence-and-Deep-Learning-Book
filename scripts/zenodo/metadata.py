"""Build the InvenioRDM metadata payloads for chapter and book records."""

from datetime import date
from pathlib import Path

CHAPTER_RESOURCE_TYPE = "publication-section"
BOOK_RESOURCE_TYPE = "publication-book"
# Same publisher as the records deposited in June 2026.
PUBLISHER = "Zenodo"


def concept_doi_for(draft: dict, version_doi: str) -> str:
    """The concept DOI Zenodo gives the draft's parent record once published."""
    # Zenodo formats every DOI it mints as "{prefix}/zenodo.{id}" (its
    # DATACITE_FORMAT setting); the concept DOI uses the parent record's id.
    prefix = version_doi.split("/", 1)[0]
    return f"{prefix}/zenodo.{draft['parent']['id']}"


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
        _related(book_doi, "doi", "ispartof", BOOK_RESOURCE_TYPE),
        _related(github_url, "url", "issupplementedby", "software"),
    ]
    if ch.get("youtube_url"):
        related_identifiers.append(
            _related(ch["youtube_url"], "url", "issupplementedby", "video")
        )

    return _record_payload(
        book_config,
        resource_type=CHAPTER_RESOURCE_TYPE,
        entry=ch,
        related_identifiers=related_identifiers,
        version=version,
        publication_date=publication_date,
    )


def build_book_payload(
    book_config: dict,
    chapter_concept_dois: list[str],
    version: str,
    publication_date: str | None = None,
) -> dict:
    """Build the InvenioRDM draft payload for the book record."""
    related_identifiers = [
        _related(book_config["github_url"], "url", "issupplementedby", "software"),
        *(_related(doi, "doi", "haspart", CHAPTER_RESOURCE_TYPE) for doi in chapter_concept_dois),
    ]
    return _record_payload(
        book_config,
        resource_type=BOOK_RESOURCE_TYPE,
        entry=book_config,
        related_identifiers=related_identifiers,
        version=version,
        publication_date=publication_date,
    )


def _record_payload(
    book_config: dict,
    *,
    resource_type: str,
    entry: dict,
    related_identifiers: list[dict],
    version: str,
    publication_date: str | None,
) -> dict:
    """Fields shared by chapter and book records; `entry` is a chapter or the book config."""
    return {
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": True},
        "metadata": {
            "resource_type": {"id": resource_type},
            "title": entry["title"].strip(),
            "publication_date": publication_date or date.today().isoformat(),
            "publisher": PUBLISHER,
            "version": version,
            "description": entry["description"].strip(),
            "creators": to_rdm_creators(entry["authors"]),
            "subjects": [{"subject": keyword} for keyword in entry.get("keywords", [])],
            "rights": [{"id": book_config["license"]}],
            "languages": [{"id": book_config["language"]}],
            "related_identifiers": related_identifiers,
        },
    }
