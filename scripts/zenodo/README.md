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
- **`create.py`** creates a Zenodo draft per chapter, reserves its DOI, uploads the chapter PDF and notebook, submits the draft to the community for review, and writes the DOI to `zenodo_summary.json`.
  It uses Zenodo's InvenioRDM REST API; the record is published when a community curator accepts the review request.
- **`inject.py`** injects DOI citations into notebook front-matter cells and updates the chapter table in `citing.qmd`.

A shared module (`common.py`) provides path constants, config/summary I/O, and chapter filtering.

```
scripts/zenodo/
  config.yaml          # human-edited: chapters, authors, metadata
  zenodo_summary.json  # machine-generated: deposit IDs and DOIs
  common.py            # shared: path constants, config/summary I/O
  render_pdf.py        # render a single chapter PDF via Quarto profiles
  create.py            # create Zenodo drafts, upload files, submit for community review
  inject.py            # inject DOIs into notebooks + citing.qmd
  test_create.py       # unit tests for the create.py metadata mapping
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

Sandbox and production use separate accounts and separate tokens.
`.env` holds one `ZENODO_TOKEN`, so swap it when switching between `--sandbox` and production.

### Zenodo Community

Every chapter record is submitted to the community named by `book.community` in `config.yaml` (`nasa-earthrise`).
`create.py` stops before creating anything if that community does not exist on the target host.

The sandbox needs its own `nasa-earthrise` community, because sandbox and production are separate systems.
Give it the same settings as production so sandbox runs behave like production runs:

- Record submission: members only.
- Review policy: curators, managers, and owners may publish without review.

`create.py` always asks for a review (`require_review: true`), so a record is never published until someone accepts the request, even for managers.

## Workflow: Adding a New Chapter

Replace `<ID>` with the chapter id (e.g., `ch10.2`) in all commands below.

### 1. Add chapter to config.yaml

Add an entry under `chapters:` with all metadata (id, title, authors, notebook path, etc.).
Use `authors: []` as a placeholder if the author list is not yet available.

Write each author as `Last, First`, with an `affiliations` list holding one item per affiliation, exactly as it should appear on Zenodo:

```yaml
authors:
  - name: "LaHaye, Nicholas"
    orcid: "0000-0001-6584-7315"
    affiliations: ["Jet Propulsion Laboratory", "Spatial Informatics Group"]
  - name: "Harvie, Julia E."
    orcid: "0009-0004-7463-0176"
    affiliations: ["Great Lakes Forestry Centre, Natural Resources Canada"]
```

Separate organizations are separate items.
A unit and its parent organization, or two names for the same organization, form one item.
The older single-string `affiliation:` key is rejected; chapters deposited before September 2026 still use it and are converted when they get a new version.

### 2. Render the chapter PDF

```bash
python scripts/zenodo/render_pdf.py <ID>
```

This creates a temporary Quarto profile, renders just that chapter to PDF, and places the output in `_book/`.
The `--no-clean` flag is used internally to preserve existing HTML output.

### 3. Create the Zenodo record and submit it for review

Test on sandbox first (with the sandbox token in `.env`):

```bash
python scripts/zenodo/create.py --chapter <ID> --dry-run
python scripts/zenodo/create.py --chapter <ID> --sandbox
```

The dry run prints the full metadata payload without calling Zenodo.
The sandbox run prints the draft URL, the reserved DOI, and the review request URL.
Open the review request (or the community's Requests tab), check the draft, and accept it.
Accepting publishes the record into the community with the reserved DOI.

The sandbox run writes its DOI to `zenodo_summary.json`.
Discard that entry before the production run:

```bash
git checkout scripts/zenodo/zenodo_summary.json
```

When ready for production, swap `.env` to the production token and run:

```bash
python scripts/zenodo/create.py --chapter <ID>
```

Then accept the request at [zenodo.org/communities/nasa-earthrise/requests](https://zenodo.org/communities/nasa-earthrise/requests).

`create.py` looks for the chapter PDF in `_book/` by default (output of `render_pdf.py`).
Use `--pdf-dir` to override with a custom PDF location.
On Zenodo the PDF is named `<pdf_prefix>_<pdf_folder>.pdf`, matching the chapters deposited in June 2026.

If a step fails after the draft is created, the draft is left on Zenodo and the script has printed its URL.
Delete it from the uploads page before rerunning, or the rerun creates a second draft.
A draft with an open review request must have the request cancelled before it can be deleted.

### 4. Inject DOIs into notebooks

Run this only after the review request is accepted, because the DOI does not resolve until the record is published.

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

- `quarto render` (default) renders the full book using the `book` profile.
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
  --pdf-dir PATH       Override PDF location (default: _book/)
  --skip-preflight     Skip the file/author readiness check
```

Without `--chapter`, processes all chapters not yet in `zenodo_summary.json`.
Chapters with empty `authors` in config.yaml will cause the script to exit before any API calls.
A chapter PDF must exist (either in `_book/` or `--pdf-dir`) before a deposit can be created.
Author names must be written as `Last, First`; any other form stops the run before any API call.
There is no publish flag: records are published by accepting the community review request.

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

## Running Tests

`test_create.py` covers the metadata mapping in `create.py` (author name splitting, the `affiliations` list, ORCID handling, payload shape).
It uses Python's built-in `unittest` and makes no network calls.
From the repo root:

```bash
python -m unittest discover -s scripts/zenodo -p "test_*.py" -v
```

From inside `scripts/zenodo`:

```bash
python -m unittest -v test_create
```
