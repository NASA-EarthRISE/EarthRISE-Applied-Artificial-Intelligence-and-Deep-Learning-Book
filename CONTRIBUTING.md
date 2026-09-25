# Contributing a Chapter

Thank you for contributing to the EarthRISE Applied AI and Deep Learning Book. This guide covers the requirements for adding a new chapter and offers suggestions for notebook structure and data handling.

## Requirements

### Folder Structure

Each chapter lives inside a top-level **section** folder. Sections and sub-chapters follow this naming convention:

```
NN_Section_Name/
  NN__Chapter_Name/
    notebooks/
      Your_Notebook.ipynb
      images/
        figure1.png
        figure2.png
    data/              # optional, for data files (.tif, .csv, etc.)
```

- Section folders use a **single underscore** after the number: `06_Eco_Process_Sim`
- Chapter folders use a **double underscore** after the number: `01__Active_Fire_Detection`
- Use underscores, not hyphens, in all folder names

Each chapter should include:

- **`notebooks/`** - one primary Jupyter notebook with pre-computed cell outputs
- **`notebooks/images/`** - chapter images stored locally (not hosted on external repos)
- **`data/`** (optional) - data files (.tif, .csv, etc.) used by the notebook

### Chapter Numbering

The book uses **hierarchical Section.Chapter numbering**. Your chapter title must include the section and chapter number as a prefix:

```markdown
# 3.1 Crop Mapping - Rice Mapping in Bhutan with U-Net
```

The section number matches the top-level folder (`03_` = Section 3), and the chapter number matches the sub-folder (`01__` = Chapter 1 within that section). If you are adding the first chapter to a new section, it would be `N.1`.

### Image Hosting

Store all chapter images in `notebooks/images/` within your chapter directory. Use markdown image syntax (not HTML `<img>` tags) so images render correctly in both HTML and PDF:

```markdown
![Description of the figure for accessibility](images/figure1.png){width="60%" fig-align="center"}
```

Do **not** host images on external repositories or reference them via URLs. All images must include a descriptive alt text for accessibility.

### Updating `_quarto.yml`

After adding your chapter folder, register your notebook in `_quarto.yml` under the appropriate section `part:`. For example:

```yaml
- part: "5. Time Series"
  chapters:
    - 05_Time_Series/01__Soybean_Yield_Prediction/notebooks/Crop_yield_estimationR4.ipynb
```

If you are adding a chapter to a section currently marked "(coming soon)", remove that label from the part title.

### PDF Compatibility

YouTube video embeds must be wrapped in a format guard so they render correctly in both HTML and PDF:

```markdown
::: {.content-visible when-format="html"}
{{< video https://www.youtube.com/embed/VIDEO_ID >}}
:::

::: {.content-visible when-format="pdf"}
Watch the video walkthrough for this chapter at [https://www.youtube.com/watch?v=VIDEO_ID](https://www.youtube.com/watch?v=VIDEO_ID)
:::
```

## Notebook Structure

Chapters should include the following elements in order:

1. **YAML frontmatter** (raw cell) with author names, ORCIDs, affiliations, `license: "CC BY 4.0"`, and citation metadata
2. **Title heading** with Section.Chapter prefix, followed by Colab and GitHub badges
3. **Author attribution** (markdown cell) for PDF output using `content-visible when-format="pdf"`
4. **Citation/DOI callout** (markdown cell) with a Zenodo DOI badge (coordinated with the editors after acceptance)
5. **Video embed** with PDF format guard (added by the editors after the chapter video is produced)
6. **Chapter content**
7. **Acknowledgements section** at the end for funding attribution

See Ch 6.1 (`06_Eco_Process_Sim/01__Active_Fire_Detection/notebooks/BNN_Active_Fire_Detection.ipynb`) for a complete example.

## Data Hosting

We recommend hosting large datasets and model weights on a cloud platform (Google Cloud Storage, Hugging Face, Zenodo, etc.) and downloading them at runtime in the notebook. This keeps the repository lightweight.

Bundling small files directly in a `data/` folder is also fine.

## License

This book is distributed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Contributed chapters are published under the same license.

## Questions

If you have questions about contributing, reach out to the editors: Tim Mayer, Biplov Bhandari, or David Saah.
