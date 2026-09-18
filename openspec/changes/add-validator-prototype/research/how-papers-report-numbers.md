# How life-science papers report numbers, and what that means for the extractor

Builds on ADR-0040 and the 2026-09-09 probe; nothing there is repeated. Six open-access papers were fetched from Europe PMC as JATS XML and inspected mechanically (section tree, tables, captions, every sentence carrying a number with a unit, every bibliographic `xref` attached to a number). Sample at the end; XML under the scratchpad only.

## 1. Where the value sits, and whether the conditions sit with it

The convention (ICMJE: Methods "sufficiently detailed" to reproduce; Results "emphasize or summarize only the most important observations", do not restate tables — https://www.icmje.org/recommendations/browse/manuscript-preparation/preparing-for-submission.html; and the same rule in writing guides: "data ... are presented in figures and tables, with a limited amount presented in the text", https://pmc.ncbi.nlm.nih.gov/articles/PMC6635678/) predicts exactly the pattern observed: **the number lives in a table or figure, the prose carries a summary or the extremes, and the fixed conditions (temperature, shaking, strain genotype, medium recipe) live only in Methods.**

| Paper | Where the headline value is stated | Conditions beside it | Only in Methods |
|---|---|---|---|
| PMC3146540 | Table 1 (24 rows); Results prose restates extremes ("between 1.6 µm for stationary cells and 3.9 µm for cells growing on LB medium") | medium, carbon source, stress, growth rate as row labels; strain in footnote | 37 °C, 300 rpm, M9 recipe, steady-state passaging |
| PMC13343645 | Table 1 (µmax and DT per medium); restated in Results ("39 ± 1 min") and, rounded, in Discussion ("30–40 min") | medium as column header | 37 °C, 250 rpm, baffled flasks, DT = ln2/µ from regression on ln OD |
| PMC4888949 | Abstract (">2300 proteins", "22 ... conditions"); per-protein copy numbers only in Supplementary Tables (absent from XML); prose gives ranges ("approx. 10 to >10000 copies per cell") | strain named once in Results | media, 37 °C, chemostat dilution rates 0.12–0.5 |
| PMC4824857 | Abstract ("∼100 million molecules-per-cell"); Results prose per protein ("Cdc23 ... 830 cpc", "∼60 cpc (IRS4) to 4.4 × 10^6 cpc (PDC1)"); no table in XML | "for cells growing in chemostat culture" | strain BY4742, F1 minimal medium, 10 g/l glucose, D = 0.1/h |
| PMC4843128 | Results prose ("λac ≈ 0.76 h−1, or 55 min per doubling"); Extended Data Tables 1–3 (strains, fitted parameters) | none in the sentence; strain in Extended Data Table 1 | bioreactor 37 °C; batch growth **offloaded to another paper**: "Batch culture growth has been described in detail previously27." |
| PMC3910158 | Abstract and prose ("3–4 million proteins per cell"); Table 1 compiles *other* papers' values with BNIDs | table notes ("40 min doubling time", "Growth at 30°C") | no Methods section exists |

Regularities across the six:

- **Tables carry the varying condition; Methods carry the fixed ones.** In no paper did a value-bearing sentence or cell also name the temperature. Temperature, aeration, vessel and genotype must be fetched from Methods every time and are shared by all values in the paper.
- **The same value is stated two to three times** at decreasing precision: table (39 ± 1), Results (39 ± 1), Discussion (30–40). The table is authoritative; the prose paraphrases it.
- **Prose ranges are ranges over conditions, not uncertainty.** "1.5 to 4.4 fl" is the smallest and largest row of Table 1; "30–34 min" spans four media.
- **A paper matched by search may not state the value at all.** PMC13343645 (2026) compares *E. coli* and *V. natriegens*; every E. coli growth curve is in Fig. 1B and the E. coli doubling time appears nowhere as a number. A "doubling time of E. coli" query ranks it highly; the extractor must return nothing.
- **Nature-family "Extended Data" is in the XML** (PMC4843128: three tables, seven figures), unlike supplementary files.
- **Violation of the Methods convention**: PMC4843128 cites a prior paper for its batch culture conditions, so temperature and medium of the headline measurement are recoverable only via ref 27. The schema needs "condition stated by reference to [REF]" as a state distinct from "unstated".

## 2. Measured, cited, derived, or parameter: cues in the text

Citation-function classification (Teufel, Siddharthan & Tidhar 2006, https://aclanthology.org/W06-1613/) reads cue phrases, first-person pronouns and tense to separate "uses the cited data" (PUse) from comparison and neutral mentions; hedging lexicons (Hyland 1998, https://benjamins.com/catalog/pbns.54) mark estimates: *approximately, ~, estimate, assume*. Both transfer directly. From the sample:

**(a) Measured here.** Past tense, first person or passive with a measurement verb, an uncertainty term, a pointer to own table/figure, and **no bibliographic `xref` on the number**. "we found the cell width to be condition-independent (1.26 µm ±0.16 µm)"; "In MSM, a lower µmax of 1.07 ± 0.03 h⁻¹ was observed, resulting in a doubling time of 39 ± 1 min"; "the proteome fraction of LacZ in the sample was determined to be 3.3%±0.3%". Location: Results, table body, table footnote. A number in Methods is almost never a result.

**(b) Cited from prior work.** A `<xref ref-type="bibr">` inside the same clause as the number; *reported, previously, in the literature, known, has been*; present perfect; located in Introduction or Discussion. "reported values below 10 min under optimal conditions [REF]" (PMC13343645, Intro; the paper's own measurement is 30–39 min); "the volume was determined to range from 0.5–4 µm3 [REF], [REF], [REF], [REF]" (PMC3146540, Intro). Comparison sentences mix both: "Consistent with the literature, the length of the cells varied ... between 1.6 µm ... and 3.9 µm (Table 1)" is a measurement wearing a citation cue; the tell is the pointer to the paper's own table and the absence of `xref` on the numbers. **Rule: an `xref` on the number outranks any verb.** Where a value carries both an `xref` and "Table 1", label it measured but flag the comparison.

**(c) Derived or estimated.** *estimate, extrapolate, corresponding to, or, calculated as, ≈, back-of-the-envelope, assuming*; often a second number in the same sentence with a conversion. "λac ≈ 0.76 h−1, or 55 min per doubling" (the h⁻¹ is fitted, the minutes are arithmetic); "Because our quantification of 1167 proteins sums to 54 million cpc, we can extrapolate ... to calculate an estimated sum of about 100 million cpc for the entire proteome" (one sentence, one measured sum and one extrapolation). PMC3910158 is derivation throughout: "Assuming an average amino acid mass of 110 Da ... we arrive at".

**(d) Parameter or input.** In Methods or a modelling section; *we used, was set, assuming, scaled to*; no uncertainty. "we used an average cell width of 1.26 µm for all conditions" (PMC3146540 — a measurement one sentence earlier, now a parameter); "assuming the average yeast cell contains 60,000 total mRNA copies ([REF])" (PMC4824857 — a cited value used as input; the authors add "We caution that this is an estimate"); "Model parameters calibrated from bioreactor" (PMC4843128, Extended Data Table 2 — fitted, a hybrid to label FITTED rather than MEASURED).

What the extractor may label FOUND: category (a) only, plus (c) when the derivation's inputs are (a) values from the same paper *and* the label carries the derivation. Categories (b) and (d) are never FOUND for this paper; (b) is a pointer to another paper.

## 3. Conditions that materially change the value

The sample shows the spans directly:

- **Strain/genotype.** BW25113 vs MG1655 on glucose: 0.60 vs 0.67 h⁻¹ (PMC3146540 Table 1). Auxotrophies (BY4742, PMC4824857) change the medium.
- **Medium and carbon source.** Galactose 0.17 to LB 1.61 h⁻¹, ten-fold in one table; complex vs minimal alone separates 30–34 from 39 min (PMC13343645).
- **Growth phase / rate / culture mode.** Stationary 1.5 fl vs LB exponential 4.4 fl; PMC4824857 attributes its higher protein-per-mRNA partly to "slower growth rates in chemostat cell cultures compared with batch/rich media". Bremer & Dennis is the canonical statement that most E. coli cell parameters are functions of doubling time (https://doi.org/10.1128/ecosal.5.2.3).
- **Temperature.** 30, 37 and 42 °C all appear; PMC3910158's table footnotes "Growth at 30°C" to explain a low proteome count.
- **Aeration, pH, osmolarity** as stress rows (anaerobic 0.55, pH 6 0.50, 50 mM NaCl 0.65 h⁻¹).
- **Plasmid burden.** The E. coli in PMC13343645 and PMC3146540 both carry a GFP plasmid.
- **Normalisation basis.** Per cell, per OD, per volume, per dry weight; PMC3910158 exists because per-cell counts disagreed five- to ten-fold once converted per volume.
- **Method and calibration.** Formaldehyde fixation shrinks cells (PMC3146540); MS counts "scaled to 60 million copies per cell" (PMC4824857). For enzyme kinetics STRENDA's minimum (temperature, pH, buffer, metal salts, substrate range, enzyme concentration) applies: https://www.beilstein-institut.de/en/projects/strenda/guidelines/.

Required: organism, strain, medium/carbon source, temperature, growth phase or rate, culture mode, normalisation basis, method. The rest is property-specific.

## 4. Several values in one paper: records versus range

- **A table with a condition axis is n records.** PMC3146540 Table 1 is 24 growth rates and 24 volumes; file the relevant rows separately, or one entry with a "Table 1" locator and the row set as range-over-conditions. Never a single mean.
- **A prose range whose endpoints belong to different conditions is a summary, not a measurement.** "1.5 to 4.4 fl", "30–34 min", "approx. 10 to >10000 copies per cell". Record as `range_over_conditions` with the endpoint conditions named, or resolve to the rows. Filing such a sentence as one interval is how BNID 109252's fused range arose.
- **mean ± SD is one record**; the ± is uncertainty and is kept.
- **"X in A vs Y in B" is two records**, and often one is measured and one cited (PMC13343645 Intro vs Results).
- **A range compiled from the literature is zero records from this paper** ("0.5–4 µm3 [REF]...[REF]"; all of PMC3910158 Table 1).
- **The same value at decreasing precision is one record**, sourced to the most precise statement.

## 5. The distractor

Hard-but-fair distractors come from the four confusions in section 2 and the condition axis in section 3:

1. **Adjacent condition, same property, same units.** True: Table 1 row "glucose | 0.60±0.05"; distractor: row "glucose MG1655 | 0.67±0.05" (PMC3146540). Or true "In MSM ... doubling time of 39 ± 1 min"; distractor "Across complex media ... doubling times of approximately 30–34 min" (PMC13343645). Fair because the deciding word (strain, medium) is present.
2. **Cited value from the Introduction.** True: the measured 30–39 min; distractor: "V. natriegens exhibits the fastest known doubling time ... below 10 min under optimal conditions [REF]". Tests whether the reviewer notices the `xref` and tense.
3. **Different quantity, shared unit and subject.** True: "a total protein count of ∼100 million molecules-per-cell"; distractor: "a median of ∼1000 proteins-per-transcript" (PMC4824857, same abstract sentence). True: cell width 1.26 µm; distractor: cell length 1.6–3.9 µm.
4. **Parameter or assumption sentence.** True: "we found the cell width to be condition-independent (1.26 µm ±0.16 µm)"; distractor: "we used an average cell width of 1.26 µm for all conditions". Same number, one is the measurement, one is its reuse. Hard, but a curator can tell them apart and the distinction is exactly what the schema needs.
5. **The other half of a derivation sentence.** True: "our quantification of 1167 proteins sums to 54 million cpc"; distractor: "an estimated sum of about 100 million cpc for the entire proteome" (PMC4824857). Both are the authors' own numbers; only one is measured.

**Must not be a distractor:** (i) another legitimate statement of the same value at any precision ("39 ± 1 min" in prose when the cell is the truth; "30–40 min" in the Discussion); (ii) the same value for the same conditions by another method; (iii) a text whose deciding condition lives only in Methods, so neither text contains it; (iv) two rows differing only in something the question did not specify (chemostat µ = 0.5 vs batch glucose 0.60 h⁻¹ when no culture mode was asked). Rule: **the distractor must differ from the true text in a dimension named in the question or visible in the two texts, and must not itself support the value.** Enforce (i) mechanically: reject any candidate containing the target value, its rounding, or its unit-converted form.

## 6. What a biologist reviewer needs in under a minute

- The **value highlighted inside each text**, the paper's own term for the property (µmax, DT, cpc) beside the question's, and any unit conversion shown (0.76 h⁻¹ → 55 min).
- **Section label and container** per text: "Results › Table 1, row 'glucose'", "Introduction, cited [ref 3]". Section alone decides most of section 2.
- **Citation markers kept as visible tokens.** Stripping `xref` turns a cited value into an apparent measurement.
- **One condition block above both texts**: organism, strain, medium, temperature, phase, marked "from Methods" or "by reference to [27]" where it came from elsewhere.
- **Texts of one to three sentences**; a table row as header→cell pairs, not the whole table.

They click through when: both texts contain the number; a text exceeds ~80 words; there is no section label; they must compute ln2/µ; the pair differs only in Methods; or the "true" text paraphrases a table they cannot see. Show the cell, not the prose restating it.

## 7. Paper types that break the task, and cheap exclusion

- **Reviews and perspectives**: every number is category (b) or (c). PMC3910158 is an *Insights & Perspectives* essay with no Methods section, whose Table 1 lists other papers' values with BNIDs, and **Europe PMC tags it `research-article`** (`pubTypeList`: "research-article, Journal Article"). Metadata alone misses it; the XML `<subj-group subj-group-type="heading"><subject>` says "Insights & Perspectives", and the absence of any `sec` titled Methods/Materials is a second cheap tell.
- **Meta-analyses and unification papers** (Ho et al. 2018, `pubTypeList` "Meta-Analysis") are catchable: `PUB_TYPE:"meta-analysis"` returns it (verified). `PUB_TYPE:"review"` and `PUB_TYPE:"review-article"` both match a tagged review (verified on PMC12983252). Add `NOT PUB_TYPE:"editorial"`, `NOT PUB_TYPE:"comment"`, `NOT SRC:PPR` (preprints). Field syntax: https://europepmc.org/searchsyntax; REST: https://europepmc.org/RestfulWebService.
- **Modelling papers** (PMC4843128) cannot be excluded by type; they contain real measurements and fitted parameters side by side. Exclude per value using the cues in section 2(d) and the presence of a "parameters" table.
- **Applied papers** (PMC13343645) match property queries while stating the value only for the *other* organism or only in a figure. No metadata catches this; "nothing to extract" must be a first-class outcome, as ADR-0040 argues for "cannot confirm".
- **JATS `article-type`** on the root (https://jats.nlm.nih.gov/archiving/tag-library/1.3/attribute/article-type.html) is the in-XML equivalent and carries the same mis-tag: PMC3910158 declares `research-article`.

## Sample

| PMC id | Title | Looked at |
|---|---|---|
| PMC3146540 | Condition-dependent cell volume and concentration of E. coli (PLoS One 2011) | section tree, Table 1 (24 rows, footnote), Results prose, Methods, Intro citations |
| PMC4888949 | The quantitative and condition-dependent E. coli proteome (Nat Biotechnol 2016) | abstract, Results ranges, Methods (genotype, media, chemostat), supplementary pointers |
| PMC4824857 | Direct and absolute quantification of over 1800 yeast proteins via SRM (Mol Cell Proteomics 2016) | abstract, cpc statements, derivation sentence, "Yeast Growth" methods |
| PMC4843128 | Overflow metabolism in E. coli results from efficient proteome allocation (Nature 2015) | λac sentence, Methods ("described previously"), Extended Data Tables 1–3 |
| PMC3910158 | What is the total number of protein molecules per cell volume? (BioEssays 2013) | subject heading, section tree (no Methods), Table 1, BNID usage, `pubTypeList` |
| PMC13343645 | Evaluation of Vibrio natriegens as a fast-growing host for plasmid DNA production (Microb Cell Fact 2026) | Table 1, every E. coli sentence with a number, Fig. 1 caption, Methods (DT formula), Intro citation |

Metadata checks used `resultType=core` and the `PUB_TYPE` queries above. Extraction scripts sit beside this file in `research/`.
