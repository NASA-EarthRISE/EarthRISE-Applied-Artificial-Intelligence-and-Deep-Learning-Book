# Zenodo DOI Pipeline

Scripts for creating Zenodo deposits and injecting DOI citations into chapter notebooks.

## Design

Two data files serve as the single source of truth:

- **`config.yaml`** (human-edited) defines all book and chapter metadata: titles, authors, ORCIDs, affiliations, descriptions, keywords, and notebook paths.
  To add a new chapter, add an entry here.
- **`zenodo_summary.json`** (machine-generated) records the Zenodo deposit IDs and DOIs created by `create.py`.
  Both files are tracked in git.

Three scripts operate on these files:

- **`render_pdf.py`** renders a single chapter as a standalone PDF using a temporary Quarto profile.
- **`create.py`** creates Zenodo deposits, uploads the chapter PDF and notebook, and writes DOIs to `zenodo_summary.json`.
- **`inject.py`** injects DOI citations into notebook front-matter cells and updates the chapter table in `citing.qmd`.

A shared module (`common.py`) provides path constants, config/summary I/O, and chapter filtering.

```
scripts/zenodo/
  config.yaml          # human-edited: chapters, authors, metadata
  zenodo_summary.json  # machine-generated: deposit IDs and DOIs
  common.py            # shared: path constants, config/summary I/O
  render_pdf.py        # render a single chapter PDF via Quarto profiles
  create.py            # create Zenodo deposits, upload PDF + notebook
  inject.py            # inject DOIs into notebooks + citing.qmd
  requirements.txt     # Python dependencies
  .env.example         # template for Zenodo API token
```

## Prerequisites

Install dependencies:

```bash
pip install -r scripts/zenodo/requirements.txt
```

Quarto must be installed for PDF rendering (`render_pdf.py`).

### Zenodo API Token

Create a `.env` file at the repo root (already gitignored):

```bash
cp scripts/zenodo/.env.example .env
# Edit .env and add your token
```

Or export directly:

```bash
export ZENODO_TOKEN="your_token_here"
```

To get a token:
1. Go to [zenodo.org](https://zenodo.org) (or [sandbox.zenodo.org](https://sandbox.zenodo.org) for testing).
2. Navigate to Settings > Applications > Personal access tokens.
3. Create a token with scopes: `deposit:write` and `deposit:actions`.

## Workflow: Adding a New Chapter

Replace `<ID>` with the chapter id (e.g., `ch10.2`) in all commands below.

### 1. Add chapter to config.yaml

Add an entry under `chapters:` with all metadata (id, title, authors, notebook path, etc.).
Use `authors: []` as a placeholder if the author list is not yet available.

### 2. Render the chapter PDF

```bash
python scripts/zenodo/render_pdf.py <ID>
```

This creates a temporary Quarto profile, renders just that chapter to PDF, and places the output in `_book/`.
The `--no-clean` flag is used internally to preserve existing HTML output.

### 3. Create the Zenodo deposit

Test on sandbox first:

```bash
python scripts/zenodo/create.py --chapter <ID> --sandbox --dry-run
python scripts/zenodo/create.py --chapter <ID> --sandbox
```

Review the draft at [sandbox.zenodo.org/me/uploads](https://sandbox.zenodo.org/me/uploads), then publish:

```bash
python scripts/zenodo/create.py --chapter <ID> --sandbox --publish
```

When ready for production:

```bash
python scripts/zenodo/create.py --chapter <ID>
python scripts/zenodo/create.py --chapter <ID> --publish
```

`create.py` looks for the chapter PDF in `_book/` by default (output of `render_pdf.py`).
Use `--pdf-dir` to override with a custom PDF location.

### 4. Inject DOIs into notebooks

Preview changes:

```bash
python scripts/zenodo/inject.py --chapter <ID> --dry-run
```

Apply:

```bash
python scripts/zenodo/inject.py --chapter <ID>
```

This injects:
- A Quarto citation YAML block into the notebook's raw front-matter cell.
- A DOI badge callout cell (visible in HTML output only) after the front-matter.
- A new row in `citing.qmd`'s chapter table.

## Quarto Profile Setup

Individual chapter PDF rendering uses Quarto profiles.
The book's chapter list lives in `_quarto-book.yml` (the default profile), not in `_quarto.yml`.
This separation lets `render_pdf.py` create a temporary profile for one chapter without affecting the full book render.

- `quarto render` (default) renders the full book as HTML using the `book` profile.
- `render_pdf.py` creates a temporary `_quarto-chpdf.yml` profile, renders one chapter to PDF, and deletes the temporary file.

## CLI Reference

### render_pdf.py

```
python scripts/zenodo/render_pdf.py <ID> [--dry-run]
```

Renders a single chapter as a standalone PDF in `_book/`.

### create.py

```
python scripts/zenodo/create.py [OPTIONS]

Options:
  --chapter ID         Process only this chapter
  --dry-run            Simulate without calling the Zenodo API
  --sandbox            Use sandbox.zenodo.org instead of production
  --publish            Publish deposits (default: leave as drafts)
  --pdf-dir PATH       Override PDF location (default: _book/)
  --skip-preflight     Skip the file/author readiness check
```

Without `--chapter`, processes all chapters not yet in `zenodo_summary.json`.
Chapters with empty `authors` in config.yaml will cause the script to exit before any API calls.
A chapter PDF must exist (either in `_book/` or `--pdf-dir`) before a deposit can be created.

### inject.py

```
python scripts/zenodo/inject.py [OPTIONS]

Options:
  --chapter ID         Process only this chapter
  --dry-run            Preview changes without writing files
```

Without `--chapter`, processes all chapters that have a DOI in `zenodo_summary.json`.
Already-injected notebooks are detected and skipped (idempotent).

## Preflight Check

`create.py` runs a preflight check before creating deposits (skip with `--skip-preflight`).
It reports:
- Whether each chapter has authors listed in config.yaml.
- Whether a PDF exists for each chapter.
- Whether notebook files exist in the repo.

The preflight check is informational only.
The actual hard blockers are the empty-authors validation and the PDF existence check.
