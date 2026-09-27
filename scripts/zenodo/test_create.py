import json
import tempfile
import unittest
from pathlib import Path

from create import (
    author_cell_problem,
    build_chapter_payload,
    parse_author_name,
    to_rdm_creators,
)

BOOK_DOI = "10.5281/zenodo.20547797"
BOOK_CONFIG = {
    "license": "cc-by-4.0",
    "language": "eng",
    "github_url": "https://github.com/NASA-EarthRISE/EarthRISE-Applied-Artificial-Intelligence-and-Deep-Learning-Book",
}


def make_chapter(**overrides) -> dict:
    chapter = {
        "id": "ch10.2",
        "title": "Earth Observation Foundation Models\n",
        "notebook": "10_Future/02__Comprehensive_EOFM_Benchmarking/notebooks/Chapter.ipynb",
        "description": "<p>Chapter description.</p>\n",
        "keywords": ["foundation models", "benchmarking"],
        "youtube_url": "https://youtu.be/c7_GxZ6apqY",
        "authors": [
            {
                "name": "LaHaye, Nicholas",
                "orcid": "0000-0001-6584-7315",
                "affiliations": ["Jet Propulsion Laboratory", "Spatial Informatics Group"],
            },
        ],
    }
    chapter.update(overrides)
    return chapter


class CreatorMappingTests(unittest.TestCase):
    def test_multiword_surname_keeps_orcid_and_affiliation(self):
        creators = to_rdm_creators([
            {
                "name": "dela Torre, Daniel Marc",
                "orcid": "0000-0003-4598-224X",
                "affiliations": ["Spatial Informatics Group"],
            }
        ])
        self.assertEqual(
            creators,
            [
                {
                    "person_or_org": {
                        "type": "personal",
                        "name": "dela Torre, Daniel Marc",
                        "family_name": "dela Torre",
                        "given_name": "Daniel Marc",
                        "identifiers": [{"scheme": "orcid", "identifier": "0000-0003-4598-224X"}],
                    },
                    "affiliations": [{"name": "Spatial Informatics Group"}],
                }
            ],
            "multi-word surname must stay whole and keep ORCID and affiliation",
        )

    def test_each_list_item_is_one_affiliation(self):
        creators = to_rdm_creators([
            {
                "name": "LaHaye, Nicholas",
                "orcid": "",
                "affiliations": ["Jet Propulsion Laboratory", "Spatial Informatics Group"],
            },
            {
                "name": "Harvie, Julia E.",
                "orcid": "",
                "affiliations": ["Great Lakes Forestry Centre, Natural Resources Canada"],
            },
        ])
        self.assertEqual(
            [creator["affiliations"] for creator in creators],
            [
                [{"name": "Jet Propulsion Laboratory"}, {"name": "Spatial Informatics Group"}],
                [{"name": "Great Lakes Forestry Centre, Natural Resources Canada"}],
            ],
            "list items map one-to-one to affiliations and are never split on punctuation",
        )

    def test_empty_orcid_omits_identifiers(self):
        (creator,) = to_rdm_creators([
            {"name": "DeMilt, Ryan P.", "orcid": "", "affiliations": ["Spatial Informatics Group"]}
        ])
        person = creator["person_or_org"]
        self.assertNotIn("identifiers", person, "an empty ORCID must not be sent to Zenodo")
        self.assertEqual(person["given_name"], "Ryan P.")

    def test_name_without_last_first_format_is_rejected(self):
        for bad_name in ["Plato", "Plato, ", ", Plato"]:
            with self.subTest(name=bad_name), self.assertRaises(ValueError):
                parse_author_name(bad_name)

    def test_malformed_affiliations_are_rejected(self):
        # Without these checks an old-format entry would silently lose its
        # affiliations, and a bare string would be iterated letter by letter.
        bad_authors = {
            "old affiliation key": {"name": "Mayer, Tim", "affiliation": "NASA"},
            "string instead of list": {"name": "Mayer, Tim", "affiliations": "NASA"},
            "blank list item": {"name": "Mayer, Tim", "affiliations": ["NASA", " "]},
        }
        for case, author in bad_authors.items():
            with self.subTest(case=case), self.assertRaises(ValueError):
                to_rdm_creators([author])


class NotebookCheckTests(unittest.TestCase):
    def test_notebook_must_have_author_cell_before_deposit(self):
        # The author-attribution cell prints the author list in the PDF, so a
        # notebook without it would be deposited with an author-less PDF.
        with tempfile.TemporaryDirectory() as tmp:
            with_authors = Path(tmp, "with_authors.ipynb")
            with_authors.write_text(json.dumps({"cells": [{"id": "author-attribution"}]}))
            without_authors = Path(tmp, "without_authors.ipynb")
            without_authors.write_text(json.dumps({"cells": [{"id": "title"}]}))

            self.assertIsNone(author_cell_problem(with_authors))
            self.assertIn("author-attribution", author_cell_problem(without_authors))
            self.assertIn("cannot read", author_cell_problem(Path(tmp, "missing.ipynb")))


class PayloadTests(unittest.TestCase):
    def test_payload_matches_existing_chapter_records(self):
        payload = build_chapter_payload(
            make_chapter(), BOOK_DOI, BOOK_CONFIG, publication_date="2026-09-27"
        )
        metadata = payload["metadata"]

        # Field set of the chapters already on Zenodo (e.g. record 20547814), plus version.
        self.assertEqual(
            set(metadata),
            {
                "creators", "description", "languages", "publication_date", "publisher",
                "related_identifiers", "resource_type", "rights", "subjects", "title", "version",
            },
        )
        self.assertEqual(payload["access"], {"record": "public", "files": "public"})
        self.assertEqual(payload["files"], {"enabled": True})
        self.assertEqual(metadata["resource_type"], {"id": "publication-section"})
        self.assertEqual(metadata["title"], "Earth Observation Foundation Models")
        self.assertEqual(metadata["publication_date"], "2026-09-27")
        self.assertEqual(metadata["publisher"], "Zenodo")
        self.assertEqual(metadata["version"], "v1")
        self.assertEqual(metadata["rights"], [{"id": "cc-by-4.0"}])
        self.assertEqual(metadata["languages"], [{"id": "eng"}])
        self.assertEqual(
            metadata["subjects"], [{"subject": "foundation models"}, {"subject": "benchmarking"}]
        )
        self.assertEqual(
            metadata["related_identifiers"],
            [
                {
                    "identifier": BOOK_DOI,
                    "scheme": "doi",
                    "relation_type": {"id": "ispartof"},
                    "resource_type": {"id": "publication-book"},
                },
                {
                    "identifier": BOOK_CONFIG["github_url"]
                    + "/tree/main/10_Future/02__Comprehensive_EOFM_Benchmarking",
                    "scheme": "url",
                    "relation_type": {"id": "issupplementedby"},
                    "resource_type": {"id": "software"},
                },
                {
                    "identifier": "https://youtu.be/c7_GxZ6apqY",
                    "scheme": "url",
                    "relation_type": {"id": "issupplementedby"},
                    "resource_type": {"id": "video"},
                },
            ],
        )

        without_video = build_chapter_payload(
            make_chapter(youtube_url=None), BOOK_DOI, BOOK_CONFIG, publication_date="2026-09-27"
        )
        self.assertEqual(
            [r["resource_type"]["id"] for r in without_video["metadata"]["related_identifiers"]],
            ["publication-book", "software"],
            "a chapter without youtube_url must not get a video link",
        )


if __name__ == "__main__":
    unittest.main()
