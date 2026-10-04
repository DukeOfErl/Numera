# Harvested entries only a person would catch

A running record for the presentation: entries that passed every mechanical check — the quote
is verbatim, the value is in it, the labels are filled in — and are still wrong, misleading or
unusable as database entries. They are the argument for a human review tier.

Add to it whenever one turns up. Each entry says what the pipeline produced, why the checks
passed, what is wrong, and how sure the diagnosis is. Values and paper ids only; no passages.

| # | Paper | Entry as harvested | What is wrong | Kind |
|---|---|---|---|---|
| 1 | PMC13262867 | Cytokinetic actin ring diameter: 10.80 ± 0.61 µm (*S. pombe*), 4.15 ± 0.56 µm (*S. cerevisiae*) | Measured on physically expanded samples (expansion microscopy). The paper's own sentence says the figures corroborate a 4–4.5× expansion factor, so the real rings are about a quarter of this size. | Right quote, wrong meaning |
| 2 | PMC13262867 | Axonal actin ring spacing: 975 nm and 866 nm, organism "mouse" | Also post-expansion distances, not real ones. And the methods describe neurons from rat pups while the figure legend says mouse; the model recorded the discrepancy as a condition and labelled the entry "mouse" anyway. | Right quote, wrong meaning; organism |
| 3 | PMC13262867 | Actin cable width: 74.89 ± 12.15 nm, 66.17 ± 9.08 nm | Not wrong — this one *is* scaled back by the expansion factor. Listed because it sits beside 1 and 2: within one paper some sizes are corrected and some are not, and only the wording tells them apart. | Contrast case |
| 4 | PMC13376574 | "Buried molecular contact surface area": 477, 443, 121, 350, 90 Å² | Five entries under one name that does not say which two molecules touch (a TOG domain and a tubulin subunit, different in each). The label is true and useless; two entries are also labelled "yeast" for values computed from another group's published structure. | Label loses identity |
| 5 | PMC3496334 | Cytoplasmic diffusion coefficients (ribosomal subunits, ATP, amino acids, sugars): values with no unit | The publisher printed the column header's symbol and unit as images, so the unit is not in the text. The model rightly did not invent one; a person looking at the page reads it at once. | Information outside the text |
| 6 | PMC3940484 | Median protein copy number: 170,000 molecules per cell, organism "mouse" | The value is for one cultured fibroblast line, not for mouse cells in general. The paper never gives a Latin species name, so the label is the common name and hides the cell line. | Organism label too coarse |

## How sure

- 1, 2, 3 and 5 are read off the papers' own sentences and markup.
- 4 and 6 are a judgement about what a database entry needs to say; a biologist should confirm
  the wording.
- None has yet been put in front of the simulated reviewers, so whether a model reviewer would
  catch it is not known. That is worth measuring: a case the models miss is the stronger slide.

## Not yet examined

- PMC12069525: twelve entries named "Hyphal cell length" or "Hyphal cell width" for different
  strains or conditions. Which is the wild type is not visible in the name.
- PMC2590609: 13,000 per cell per second appears three times, as the protein synthesis rate and
  as the initiation and termination frequencies — possibly one number restated by reasoning.
