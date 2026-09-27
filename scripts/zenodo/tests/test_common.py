import json
import tempfile
import unittest
from pathlib import Path

from common import author_cell_problem


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


if __name__ == "__main__":
    unittest.main()
