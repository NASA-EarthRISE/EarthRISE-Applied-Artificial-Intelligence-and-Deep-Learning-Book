# Zenodo DOI Pipeline

Scripts for creating Zenodo deposits and injecting DOI citations into chapter notebooks.

## Design

Two data files serve as the single source of truth:

- **`config.yaml`** (human-edited) defines all book and chapter metadata: titles, authors, ORCIDs, affiliations, descriptions, keywords, and notebook paths.
  To add a new chapter, add an entry here.
- **`zenodo_summary.json`** (machine-generated) records the Zenodo deposit IDs and DOIs created by `create.py`.
  Both files are tracked in git.

Two scripts operate on these files:

- **`create.py`** reads `config.yaml`, creates Zenodo deposits, and writes DOIs to `zenodo_summary.json`.
- **`inject.py`** reads both files, injects DOI citations into notebook front-matter cells, and updates the chapter table in `citing.qmd`.

A shared module (`common.py`) provides path constants, config/summary I/O, and chapter filtering used by both scripts.

```
scripts/zenodo/
  config.yaml          # human-edited: chapters, authors, metadata
  zenodo_summary.json  # machine-generated: deposit IDs and DOIs
  common.py            # shared: path constants, config/summary I/O
  create.py            # step 1: create Zenodo deposits
  inject.py            # step 2: inject DOIs into notebooks + citing.qmd
  requirements.txt     # Python dependencies (requests, pyyaml)
```

## Prerequisites

Install dependencies:

```bash
pip install -r scripts/zenodo/requirements.txt
```

### Zenodo API Token

Both scripts require a personal API token from Zenodo.

1. Go to [zenodo.org](https://zenodo.org) (or [sandbox.zenodo.org](https://sandbox.zenodo.org) for testing).
2. Navigate to Settings > Applications > Personal access tokens.
3. Create a new token with scopes: `deposit:write` and `deposit:actions`.
4. Set the token in your shell before running:

```bash
export ZENODO_TOKEN="your_token_here"
```

The token is never stored in code or config files.

## Workflow: Adding a New Chapter

### 1. Add chapter to config.yaml

Add an entry under `chapters:` with all metadata (id, title, authors, notebook path, etc.).
Use `authors: []` as a placeholder if the author list is not yet available.

### 2. Create the Zenodo deposit

Replace `<ID>` with the chapter id (e.g., `ch10.2`).

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

To upload PDFs alongside notebooks, pass `--pdf-dir`:

```bash
python scripts/zenodo/create.py --chapter <ID> --pdf-dir ~/Desktop/PDFs
```

The `--pdf-dir` directory should contain subfolders named per chapter's `pdf_folder` value in `config.yaml`.
These are Quarto-rendered chapter PDFs stored locally, not in the book repo.

### 3. Inject DOIs into notebooks

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

## CLI Reference

### create.py

```
python scripts/zenodo/create.py [OPTIONS]

Options:
  --chapter ID         Process only this chapter (e.g., ch10.2)
  --dry-run            Simulate without calling the Zenodo API
  --sandbox            Use sandbox.zenodo.org instead of production
  --publish            Publish deposits (default: leave as drafts)
  --pdf-dir PATH       Directory with per-chapter PDF subfolders
  --skip-preflight     Skip the file/author readiness check
```

Without `--chapter`, processes all chapters not yet in `zenodo_summary.json`.
Chapters with empty `authors` in config.yaml will cause the script to exit before any API calls.

### inject.py

```
python scripts/zenodo/inject.py [OPTIONS]

Options:
  --chapter ID         Process only this chapter (e.g., ch10.2)
  --dry-run            Preview changes without writing files
```

Without `--chapter`, processes all chapters that have a DOI in `zenodo_summary.json`.
Already-injected notebooks are detected and skipped (idempotent).

## Preflight Check

`create.py` runs a preflight check before creating deposits (skip with `--skip-preflight`).
It reports:
- Whether each chapter has authors listed in config.yaml.
- Whether PDF files exist in the `--pdf-dir` directory (if provided).
- Whether notebook files exist in the repo.

The preflight check is informational only.
The actual hard blocker is the empty-authors validation, which halts execution before any Zenodo API calls.
