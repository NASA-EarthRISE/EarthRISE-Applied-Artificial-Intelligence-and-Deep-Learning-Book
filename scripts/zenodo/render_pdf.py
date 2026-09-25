"""Render a single chapter as a standalone PDF using Quarto profiles."""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

from common import REPO_DIR, load_config, filter_chapters

PROFILE_PREFIX = "_quarto-chpdf"
BOOK_PDF_FORMAT = None  # loaded from _quarto.yml at runtime


def load_pdf_format() -> dict:
    """Read the pdf format block from the book's _quarto.yml."""
    quarto_yml = REPO_DIR / "_quarto.yml"
    with open(quarto_yml, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("format", {}).get("pdf", {})


def build_profile_yaml(pdf_format: dict) -> dict:
    pdf_format = {**pdf_format, "toc": False}
    return {
        "project": {"type": "default"},
        "format": {"pdf": pdf_format},
    }


def render_chapter_pdf(chapter_id: str, dry_run: bool = False) -> Path:
    config = load_config()
    chapters = filter_chapters(config["chapters"], chapter_id)
    ch = chapters[0]

    notebook_path = ch["notebook"]
    output_name = Path(notebook_path).stem
    pdf_format = load_pdf_format()

    profile_name = PROFILE_PREFIX
    profile_path = REPO_DIR / f"_quarto-{profile_name}.yml"
    nb_full_path = REPO_DIR / notebook_path
    expected_pdf = nb_full_path.with_suffix(".pdf")
    final_pdf = REPO_DIR / "_book" / f"{output_name}.pdf"

    print(f"Rendering chapter PDF: {ch['id']} ({ch['title'][:60]})")
    print(f"  Notebook: {notebook_path}")
    print(f"  Output: _book/{output_name}.pdf")

    if dry_run:
        print("  [dry-run] would create temporary profile and render")
        return final_pdf

    profile_data = build_profile_yaml(pdf_format)
    profile_path.write_text(
        yaml.dump(profile_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    try:
        result = subprocess.run(
            [
                "quarto", "render", notebook_path,
                "--profile", profile_name,
                "--to", "pdf",
                "--no-clean",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"  ERROR: quarto render failed:\n{result.stderr[-500:]}")
            sys.exit(1)

        # With type: default, Quarto puts the PDF next to the source file.
        # Move it to _book/ where create.py expects it.
        if expected_pdf.exists():
            final_pdf.parent.mkdir(parents=True, exist_ok=True)
            expected_pdf.rename(final_pdf)
            print(f"  PDF rendered: {final_pdf.relative_to(REPO_DIR)}")
        elif final_pdf.exists():
            print(f"  PDF rendered: {final_pdf.relative_to(REPO_DIR)}")
        else:
            print(f"  WARNING: quarto succeeded but PDF not found")
            print(f"    Checked: {expected_pdf}")
            print(f"    Checked: {final_pdf}")
            sys.exit(1)

    finally:
        if profile_path.exists():
            profile_path.unlink()

    return final_pdf


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a single chapter as a standalone PDF."
    )
    parser.add_argument(
        "chapter", metavar="ID", help="Chapter id to render (e.g., ch10.2)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be rendered without running Quarto"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    render_chapter_pdf(args.chapter, dry_run=args.dry_run)
