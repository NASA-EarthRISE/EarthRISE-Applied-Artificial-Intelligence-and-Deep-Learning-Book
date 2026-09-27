import json
import tempfile
import unittest
from pathlib import Path

from inject import BADGE_CELL_ID, badge_insert_index, inject_notebook

FRONT_MATTER = ["---\n", "title: Chapter\n", "license: \"CC BY 4.0\"\n", "---"]
CHAPTER = {"title": "Chapter", "authors": [{"name": "Doe, Jane"}]}
BOOK = {"title": "Book", "year": 2026, "authors": [{"name": "Roe, John"}]}
BOOK_DOI = "10.5281/zenodo.1"


def cells(*ids: str) -> list[dict]:
    return [{"cell_type": "markdown", "id": cell_id, "source": []} for cell_id in ids]


def write_notebook(directory: str, front_matter: list[str] = FRONT_MATTER) -> Path:
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
    nb_path = Path(directory, "chapter.ipynb")
    nb_path.write_text(json.dumps(notebook), encoding="utf-8")
    return nb_path


def inject(nb_path: Path, doi: str) -> bool:
    return inject_notebook(nb_path, CHAPTER, doi, BOOK_DOI, BOOK, dry_run=False)


def read_cells(nb_path: Path) -> list[dict]:
    return json.loads(nb_path.read_text(encoding="utf-8"))["cells"]


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
        with tempfile.TemporaryDirectory() as tmp:
            nb_path = write_notebook(tmp)
            self.assertTrue(inject(nb_path, "10.5281/zenodo.2"))
            notebook_cells = read_cells(nb_path)

        raw_source = notebook_cells[0]["source"]
        self.assertEqual(raw_source[:3], FRONT_MATTER[:3], "original front-matter lines must be untouched")
        self.assertIn('  doi: "10.5281/zenodo.2"\n', raw_source)
        self.assertEqual(raw_source[-1], "---")
        self.assertTrue(all(line.endswith("\n") for line in raw_source[:-1]))

        self.assertEqual([c["id"] for c in notebook_cells][3:5], ["author-notes", BADGE_CELL_ID])
        badge_source = notebook_cells[4]["source"]
        self.assertTrue(all(line.endswith("\n") for line in badge_source))
        self.assertEqual(badge_source[0], '::: {.content-visible when-format="html"}\n')
        self.assertIn('::: {.content-visible when-format="pdf"}\n', badge_source)

    def test_pdf_citation_block_has_doi_link_but_no_badge_images(self):
        # Badge SVGs from zenodo.org do not render in the LaTeX PDF, so the PDF
        # block carries the citation text and DOI link only.
        with tempfile.TemporaryDirectory() as tmp:
            nb_path = write_notebook(tmp)
            inject(nb_path, "10.5281/zenodo.2")
            badge = "".join(read_cells(nb_path)[4]["source"])

        pdf_block = badge[badge.index('when-format="pdf"'):]
        self.assertIn("**How to cite this chapter:**", pdf_block)
        self.assertIn("https://doi.org/10.5281/zenodo.2", pdf_block)
        self.assertIn("https://doi.org/10.5281/zenodo.1", pdf_block, "the book's DOI must be cited too")
        self.assertNotIn("badge/DOI", pdf_block)

    def test_new_doi_replaces_the_old_citation_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            nb_path = write_notebook(tmp)
            inject(nb_path, "10.5281/zenodo.2")
            self.assertTrue(inject(nb_path, "10.5281/zenodo.3"), "a changed DOI must be rewritten")
            notebook_cells = read_cells(nb_path)

        front_matter = "".join(notebook_cells[0]["source"])
        self.assertEqual(front_matter.count("citation:"), 1, "the old citation block must be removed")
        self.assertIn('doi: "10.5281/zenodo.3"', front_matter)
        self.assertNotIn("10.5281/zenodo.2", front_matter)
        self.assertEqual(notebook_cells[0]["source"][:3], FRONT_MATTER[:3])

        ids = [c["id"] for c in notebook_cells]
        self.assertEqual(ids.count(BADGE_CELL_ID), 1, "the badge cell must be replaced, not duplicated")
        self.assertEqual(ids.index(BADGE_CELL_ID), 4, "the badge keeps its position")
        badge = "".join(notebook_cells[4]["source"])
        self.assertIn("10.5281/zenodo.3", badge)
        self.assertNotIn("10.5281/zenodo.2", badge)

    def test_rerun_with_same_doi_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            nb_path = write_notebook(tmp)
            inject(nb_path, "10.5281/zenodo.2")
            before = nb_path.read_bytes()
            self.assertFalse(inject(nb_path, "10.5281/zenodo.2"))
            self.assertEqual(nb_path.read_bytes(), before)

    def test_hand_written_citation_key_is_left_alone(self):
        # Adding a second `citation:` key would make the front matter invalid YAML.
        front_matter = ["---\n", "title: Chapter\n", "citation:\n", "  doi: \"10.1/manual\"\n", "---"]
        with tempfile.TemporaryDirectory() as tmp:
            nb_path = write_notebook(tmp, front_matter)
            before = nb_path.read_bytes()
            self.assertFalse(inject(nb_path, "10.5281/zenodo.2"))
            self.assertEqual(nb_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
