import json
import tempfile
import unittest
from pathlib import Path

from inject import BADGE_CELL_ID, badge_insert_index, inject_notebook


def cells(*ids: str) -> list[dict]:
    return [{"cell_type": "markdown", "id": cell_id, "source": []} for cell_id in ids]


class BadgePlacementTests(unittest.TestCase):
    def test_badge_goes_after_the_author_block(self):
        cases = {
            "after author notes when present": (
                cells("quarto-yaml-front-matter", "title", "author-attribution", "author-notes", "video"),
                4,
            ),
            "after the author list otherwise": (
                cells("quarto-yaml-front-matter", "title", "author-attribution", "gpu-note", "video"),
                3,
            ),
        }
        for case, (notebook_cells, expected) in cases.items():
            with self.subTest(case=case):
                self.assertEqual(badge_insert_index(notebook_cells), expected)

    def test_notebook_without_author_attribution_has_no_badge_position(self):
        # The badge must never land above the chapter title, which is what
        # inserting straight after the front matter would do.
        self.assertIsNone(badge_insert_index(cells("quarto-yaml-front-matter", "title", "body")))


class InjectNotebookTests(unittest.TestCase):
    def test_injection_keeps_jupyter_line_format(self):
        # Jupyter stores cell source as one string per line. Writing a single
        # joined string makes git show the whole front matter as rewritten.
        front_matter = ["---\n", "title: Chapter\n", "license: \"CC BY 4.0\"\n", "---"]
        notebook = {
            "cells": [
                {"cell_type": "raw", "id": "quarto-yaml-front-matter", "metadata": {}, "source": front_matter},
                {"cell_type": "markdown", "id": "title", "metadata": {}, "source": ["# 10.2 Chapter"]},
                {"cell_type": "markdown", "id": "author-attribution", "metadata": {}, "source": ["Authors"]},
                {"cell_type": "markdown", "id": "author-notes", "metadata": {}, "source": ["Note"]},
                {"cell_type": "markdown", "id": "body", "metadata": {}, "source": ["Body"]},
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        chapter = {"title": "Chapter", "authors": [{"name": "Doe, Jane"}]}
        book = {"title": "Book", "year": 2026, "authors": [{"name": "Roe, John"}]}

        with tempfile.TemporaryDirectory() as tmp:
            nb_path = Path(tmp, "chapter.ipynb")
            nb_path.write_text(json.dumps(notebook), encoding="utf-8")
            self.assertTrue(
                inject_notebook(nb_path, chapter, "10.5281/zenodo.2", "10.5281/zenodo.1", book, dry_run=False)
            )
            cells = json.loads(nb_path.read_text(encoding="utf-8"))["cells"]

        raw_source = cells[0]["source"]
        self.assertEqual(raw_source[:3], front_matter[:3], "original front-matter lines must be untouched")
        self.assertIn('  doi: "10.5281/zenodo.2"\n', raw_source)
        self.assertEqual(raw_source[-1], "---")
        self.assertTrue(all(line.endswith("\n") for line in raw_source[:-1]))

        self.assertEqual([c["id"] for c in cells][3:5], ["author-notes", BADGE_CELL_ID])
        badge_source = cells[4]["source"]
        self.assertEqual(len(badge_source), 10, "badge cell must be stored one line per string")
        self.assertTrue(all(line.endswith("\n") for line in badge_source))


if __name__ == "__main__":
    unittest.main()
