# Contributing a Chapter

Thank you for contributing to the EarthRISE Applied AI and Deep Learning Book. This guide covers the requirements for adding a new chapter and offers suggestions for notebook structure and data handling.

## Requirements

### Folder Structure

Each chapter lives inside a top-level **part** folder. Parts and sub-chapters follow this naming convention:

```
NN_Part_Name/
  NN__Sub_Chapter_Name/
    notebooks/
      Your_Notebook.ipynb
    pdf/
      Your_Chapter_Text.pdf
```

- Top-level parts use a **single underscore** after the number: `06_Eco_Process_Sim`
- Sub-chapters use a **double underscore** after the number: `01__Active_Fire_Detection`
- Use underscores, not hyphens, in all folder names

Each sub-chapter should include:

- **`notebooks/`** — one primary Jupyter notebook with pre-computed cell outputs
- **`pdf/`** — a companion written chapter document (PDF)

If your chapter includes small data files or trained model weights, place them in a `data/` subdirectory within your sub-chapter folder.

### Updating `_quarto.yml`

After adding your chapter folder, register your notebook in `_quarto.yml` so it appears in the rendered book. Add your notebook path under the appropriate part in the `chapters:` list. For example:

```yaml
chapters:
  - part: "Time Series"
    chapters:
      - 05_Time_Series/01__Soybean_Yield_Prediction/notebooks/Crop_yield_estimationR4.ipynb
```

Also update the Book Outline section in `README.md` to include your chapter.

## Suggestions

The following are not strict requirements, but adopting them helps maintain consistency across chapters.

### Notebook Structure

Chapters that include the following elements tend to render well in the published book:

- **YAML frontmatter** (first cell, raw or markdown) with author names, ORCIDs, affiliations, and `license: "CC BY 4.0"`
- **Colab / GitHub badges** linking to the notebook for easy access
- **Video embed** using the Quarto shortcode `{{< video https://www.youtube.com/embed/VIDEO_ID >}}` (added by the editors after the chapter video is produced)
- **Acknowledgements section** at the end of the notebook for funding attribution

See the Chapter 6 notebook (`06_Eco_Process_Sim/01__Active_Fire_Detection/notebooks/BNN_Active_Fire_Detection.ipynb`) for an example that includes all of these elements.

### Data Hosting

We recommend hosting large datasets and model weights on a cloud platform (Google Cloud Storage, Hugging Face, Zenodo, etc.) and downloading them at runtime in the notebook. This keeps the repository lightweight.

Bundling small files directly in a `data/` folder is also fine — use whichever approach works best for your workflow and audience.

### License

This book is distributed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Contributed chapters are published under the same license.

## Questions

If you have questions about contributing, reach out to the editors: Tim Mayer, Biplov Bhandari, or David Saah.
