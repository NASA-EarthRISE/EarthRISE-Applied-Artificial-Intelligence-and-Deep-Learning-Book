# Zenodo DOI Pipeline

Scripts that publish the book and each chapter as Zenodo records and put their citations into the notebooks and PDFs.

## How it works

Each chapter and the book is one Zenodo record in the [NASA EarthRISE community](https://zenodo.org/communities/nasa-earthrise).
Every record has two DOIs:

- A **concept DOI**, which always opens the latest version. The book cites this one everywhere: notebooks, PDFs, `citing.qmd`.
- A **version DOI** per version, which always opens that exact version.

When a chapter changes, it gets a new version on Zenodo; its concept DOI, and so every citation, stays the same.

Two data files are the single source of truth:

- **`config.yaml`** (edited by hand): book and chapter metadata, including titles, authors, ORCIDs, affiliations, descriptions, keywords, and notebook paths.
- **`zenodo_summary.json`** (written by the scripts): for the book and each chapter, `deposit_id` (the record ID of the latest version) and `concept_doi`.
  A chapter started with `create.py` but not yet submitted also has `"status": "draft"`.

Sandbox runs use `zenodo_summary.sandbox.json` instead, which is gitignored.

```
scripts/zenodo/
  config.yaml             # edited by hand: book, chapters, authors, metadata
  zenodo_summary.json     # written by the scripts: record IDs and concept DOIs
  render_pdf.py           # render one chapter PDF via a Quarto profile
  create.py               # new chapter: draft + DOI, then upload and submit for review
  update.py               # existing records: publish a new version
  inject.py               # write citations into notebooks and citing.qmd
  common.py               # shared: paths, config/summary I/O, chapter file helpers
  metadata.py             # builds the Zenodo metadata for chapters and the book
  zenodo_api.py           # client for Zenodo's API
  tests/                  # unit tests (no network)
  requirements.txt        # Python dependencies
  .env.example            # template for the Zenodo API token
```

## Prerequisites

Install dependencies, and install Quarto for rendering PDFs:

```bash
pip install -r scripts/zenodo/requirements.txt
```

### Zenodo API token

Create a `.env` file at the repo root (gitignored) from the template, then add your token:

```bash
cp scripts/zenodo/.env.example .env
```

To get a token, go to [zenodo.org](https://zenodo.org) (or [sandbox.zenodo.org](https://sandbox.zenodo.org) for testing), open Settings > Applications > Personal access tokens, and create a token with the scopes `deposit:write` and `deposit:actions`.

Sandbox and production are separate systems with separate accounts and tokens.
`.env` holds one `ZENODO_TOKEN`, so swap it when switching between `--sandbox` and production.

### Zenodo community

New chapters are submitted to the community named by `book.community` in `config.yaml` (`nasa-earthrise`), and `create.py` stops before creating anything if that community does not exist.
The sandbox needs its own `nasa-earthrise` community, with the same settings as production:

- Record submission: members only.
- Review policy: curators, managers, and owners may publish without review.

`create.py` always asks for a review, so a new chapter is never published until someone accepts the request, even when the submitter is a manager.

## Adding a new chapter

The DOI is reserved before the PDF is rendered, so the chapter's first PDF already carries its citation.
Commands run from `scripts/zenodo`; replace `<ID>` with the chapter id (for example `ch11.1`).

### 1. Add the chapter to config.yaml

Add an entry under `chapters:` with its id, title, notebook path, description, keywords, and authors.
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
An optional `youtube_url` adds the chapter video as a related link on Zenodo.

### 2. Prepare the notebook

Chapter notebooks start with the same cells, in this order:

| Order | Cell | Cell id | Shown in |
|---|---|---|---|
| 1 | Quarto front matter (raw cell) | `quarto-yaml-front-matter` | metadata |
| 2 | Chapter title (`# 10.2 ...`) and Colab link | any | HTML and PDF |
| 3 | Author list with ORCID links | `author-attribution` (required) | PDF only |
| 4 | Author notes, e.g. equal contribution (optional) | `author-notes` | HTML and PDF |
| 5 | "How to cite" block, added by `inject.py` | `zenodo-doi-badge` | HTML (with badges) and PDF (text and links) |

Copy the `author-attribution` cell from an existing chapter and change the names and ORCIDs:

```markdown
::: {.content-visible when-format="pdf"}
**Authors:** Jane Doe `\orcidlink{0000-0000-0000-0000}`{=latex}, John Roe
:::
```

Jupyter assigns random cell ids and has no easy way to rename them.
To set an id, open the `.ipynb` as text (in VS Code: right-click the file, **Open With...**, **Text Editor**) and change that cell's `"id"` value.
`create.py` and `update.py` stop if the `author-attribution` cell is missing, because the PDF would have no author list.

### 3. Create the draft and reserve its DOI

```bash
python create.py --chapter <ID> --dry-run
python create.py --chapter <ID>
```

The dry run prints the full metadata without calling Zenodo.
The real run creates the draft, reserves its DOI, and records the chapter in `zenodo_summary.json` with `"status": "draft"`.

### 4. Inject the citation and render the PDF

```bash
python inject.py --chapter <ID>
python render_pdf.py <ID>
git diff
```

`inject.py` adds the citation block to the front matter and the "How to cite" cell after the author block, and updates the chapter table in `citing.qmd`.
`render_pdf.py` renders the chapter to `_book/`, now including the citation.

### 5. Upload and submit for review

```bash
python create.py --chapter <ID> --submit
```

This refreshes the draft's metadata from `config.yaml` (so edits made since step 3 are included), uploads the PDF and notebook, and submits the draft for community review.
Accept the request it prints, or use the community's Requests tab; accepting publishes the chapter with the DOI reserved in step 3.

### 6. Add the chapter to the book record

The book record lists its chapters, so it needs a new version too:

```bash
quarto render --to pdf
python update.py --book
```

Run the first command from the repo root.
Then commit the notebook, `citing.qmd`, and `zenodo_summary.json`.

## Publishing new versions of existing records

Use this when a chapter's PDF or metadata changes, for example after renumbering chapters or editing the text.
Commands run from `scripts/zenodo`.

1. Update the citations if needed: `python inject.py` (all chapters) or `python inject.py --chapter <ID>`.
   It rewrites a notebook only when its citation changed.
2. Render the PDFs: `python render_pdf.py <ID>` for each chapter, and `quarto render --to pdf` from the repo root for the book.
3. Preview, then publish:

   ```bash
   python update.py --dry-run
   python update.py --chapter <ID>
   python update.py --book
   ```

   Without `--chapter` or `--book`, `update.py` processes every chapter.
4. Commit `zenodo_summary.json`, which now holds the new version IDs.

For each record, `update.py` creates the next version, sets its metadata from `config.yaml` (version label `v2`, `v3`, and so on; today's date), uploads the files fresh, prints a preview link, and asks before publishing.
If Zenodo attaches a review to the new version, it submits that instead and prints the link to accept.
If you answer no, or a run stops midway, rerun it: Zenodo returns the unfinished draft instead of creating a second one.

On Zenodo the chapter PDF is named `<pdf_prefix>_<pdf_folder>.pdf` and the book PDF `<pdf_prefix>.pdf`, matching the files deposited in June 2026.

## Sandbox rehearsal

Rehearse either workflow on sandbox.zenodo.org before production:

1. Put the sandbox token in `.env`.
2. Add `--sandbox` to `create.py`, `inject.py`, and `update.py`.
   They then read and write `zenodo_summary.sandbox.json`, so the committed summary is never touched.
3. `zenodo_summary.sandbox.json` needs a `book` entry with a `concept_doi` before any sandbox run; chapters can borrow the production book's concept DOI there.

`inject.py --sandbox` writes the sandbox DOI into the notebook and skips `citing.qmd`.
The production `inject.py` run later replaces that DOI, so never commit a notebook while it holds a sandbox DOI (`10.5072/...`).

If a step fails after a draft exists, the scripts print its URL.
Reruns continue where they stopped: `create.py` skips chapters already recorded, `create.py --submit` clears and re-uploads the draft's files, and `update.py` reuses the unfinished version.
To start over instead, delete the draft from the uploads page; a draft with an open review request must have that request cancelled first.

## Quarto profile setup

Individual chapter PDF rendering uses Quarto profiles.
The book's chapter list lives in `_quarto-book.yml` (the default profile), not in `_quarto.yml`.
This separation lets `render_pdf.py` create a temporary profile for one chapter without affecting the full book render.

- `quarto render` (default) renders the full book using the `book` profile.
- `render_pdf.py` creates a temporary `_quarto-chpdf.yml` profile, renders one chapter to PDF, and deletes the temporary file.

## CLI reference

### render_pdf.py

```
python render_pdf.py <ID> [--dry-run]
```

Renders one chapter as a standalone PDF in `_book/`.

### create.py

```
python create.py [--chapter ID] [--submit] [--dry-run] [--sandbox] [--pdf-dir PATH] [--skip-preflight]
```

Without `--submit`: creates a draft and reserves a DOI for each chapter not yet in the summary file.
With `--submit`: uploads the PDF and notebook of each chapter marked `draft` and submits it for review.
Before any API call it stops on empty authors, author names not written as `Last, First`, malformed affiliations, a missing `author-attribution` cell, or (with `--submit`) a missing PDF.
`--submit` also prints a preflight report of authors, PDF, notebooks, and author cell; `--skip-preflight` hides it.

### update.py

```
python update.py [--chapter ID | --book] [--dry-run] [--sandbox]
```

Publishes a new version of existing records: every chapter by default, one chapter with `--chapter`, or the book with `--book`.
It refuses chapters still marked `draft`; finish those with `create.py --submit`.

### inject.py

```
python inject.py [--chapter ID] [--dry-run] [--sandbox]
```

Writes each chapter's concept DOI into its notebook and rebuilds the chapter table in `citing.qmd`.
Adds the citation on the first run and updates it when the DOI changes; notebooks already up to date are left untouched.
A notebook whose front matter has its own `citation:` key is skipped, because a second key would make the YAML invalid.

## Running tests

The tests in `tests/` cover the metadata sent to Zenodo, the author-cell check, and how `inject.py` edits notebooks.
They use Python's built-in `unittest` and make no network calls.

From the repo root:

```bash
python -m unittest discover -s scripts/zenodo/tests -t scripts/zenodo -v
```

From inside `scripts/zenodo`:

```bash
python -m unittest discover -s tests -t . -v
```
