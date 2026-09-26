# Findings — reach probe, 2026-09-18

ADR-0040's next probe #1: supplementary files and figure images, "where the
missing ~78% lives". The short answer is that it does not live there.

## 1. One call returns both, and `isOpenAccess` still gates everything

`GET /{pmcid}/supplementaryFiles` returns a single zip holding supplementary
files **and** the article's figure images at 300 DPI. ADR-0040 treated these as
two separate hard problems; they are one request.

But the gate has not moved. Probed against the flag:

| | article XML | supplementary |
|---|---|---|
| `isOpenAccess=Y` (17 papers) | present | present |
| `isOpenAccess=N` (2 papers) | 151 bytes — empty | 297 bytes — empty |

**Supplementary and figures deepen the open-access slice. They do not widen
it.** ADR-0040's recommendation to filter on `isOpenAccess` before attempting
retrieval stands unchanged.

## 2. Whole-corpus reach is 19.2%, and supplementary adds 0.4%

Random sample, seed 20260918, of the 8,696 entries carrying a reference PMID and
a value or range (the same denominator ADR-0040 reports, independently
reproduced). n = 250.

| class | n | % |
|---|---|---|
| `no_pmcid` — reference does not resolve to a PMC record | 136 | 54.4% |
| `not_open` — resolves, `isOpenAccess=N`, nothing reachable | 66 | 26.4% |
| `in_article` — value occurs in the article text | 26 | 10.4% |
| `in_supplement` — not in the article, found in supplementary | **1** | **0.4%** |
| `not_found` — reachable, read, value not in any of it | 21 | 8.4% |

ADR-0040 measured 22% reachable on the *favourable* slice and predicted the
whole-corpus figure would be lower. It is 19.2%, which is close, and the
prediction holds.

**The headline: supplementary material moved exactly one entry in 250.** Of the
27 values found anywhere, 26 were already in the article text. Whatever is
blocking coverage, supplementary files are not the thing that unblocks it.

## 3. The recipe gap could not be measured, and the reason is the finding

The intended measurement — *given that we can reach the source, how often is the
corpus value actually in it* — needs papers where everything was read. There
were **4**.

Of 46 reachable papers with real article text, **42 carried material the text
path could not read** (median 15 files, max 280). `not_found` therefore cannot
be read as "the number is absent"; for 18 of 19 such entries it means "we could
not open the file it might be in".

The one clean `not_found` is recorded for a human to judge: BNID 117053,
PMC2364095, `range_low=5.0`, units `%`.

Two entries (BNID 104683, 100154, both PMC2754216) were classified `not_found`
with **zero** article text — a straightforward bug in the first pass, since an
empty fetch is not evidence of absence. They are excluded above.

## 4. What the unreadable material is — 41 bundles, 730 files, 135 MB

| ext | files | MB | papers (of 46) | readable by the text path |
|---|---|---|---|---|
| `.jpg` | 365 | 30.1 | 41 | no |
| `.gif` | 256 | 2.2 | 41 | no |
| `.pdf` | 35 | 19.5 | **16** | no |
| `.tif` | 29 | 28.6 | 6 | no |
| `.xls` | 19 | 15.3 | 5 | no — binary OLE2 |
| `.xlsx` | 7 | 12.7 | 5 | **yes** |
| `.docx` | 4 | 0.2 | 3 | **yes** |
| `.zip` | 4 | 6.0 | 3 | no — contains the real tables |
| `.eps` | 4 | 19.8 | 2 | no |
| `.doc` | 3 | 0.3 | 2 | no |

**98% of files and 90% of bytes are unreadable without another reader.**

The ordering this implies is not the one the probe set out to test:

1. **Figure images** — in 41 of 46 papers. Every paper has figures; nothing else
   is close to that reach.
2. **PDF text** — 16 of 46 papers. The largest single non-image win.
3. **Binary `.xls`** — 5 of 46 papers.

Note the shape of the spreadsheet result: the *readable* modern format `.xlsx`
appears in 5 papers and the *unreadable* legacy `.xls` in 5 more. Supporting
`.xlsx`, which this probe already does, covers about half the spreadsheets and
about a tenth of the papers.

## 5. Figures are legible, and the supplementary text can check the reading

Figure 5 of PMC5005352 (BNID 115327, whose per-depth values ADR-0040 lists as
figure-only) is a 630×577 JPEG at 300 DPI. Seven points are readable, axes and
all.

The same paper's `DataSheet1.DOCX` tabulates the exact depths, which turns a
subjective reading into a measurable one:

| supplementary table | read off the figure | error |
|---|---|---|
| 0.4 | ~0.3 | −0.1 |
| 2.75 | ~3 | +0.25 |
| 4.32 | ~4.5 | +0.18 |
| 9.57 | ~10.5 | **+0.93** |
| 14.55 | ~14.5 | −0.05 |
| 20.53 | ~20.5 | −0.03 |

Depth readings land within ~1 mbsf. **The largest error is the informative one**
and it is not random: the reader had already seen the article sentence "peaking
at 1000 fg C μm⁻³ at 10 m depth" earlier in the same session, and read 9.57 as
10.5 — pulled toward the text. That is ADR-0040's contamination problem showing
up inside a measurement, and it is why the figure arm needs agents that have not
seen the article. **No figure-reading rate should be quoted from this probe.**

## 6. The 108345/108346 recipe gap, confirmed mechanically

BNID 108345 (46429.8 g/mole) and 108346 (2.305 mM) rest on `Table S1 Quantified
proteins.xlsx`, which is reachable and parses cleanly to **413 rows — exactly the
count the paper states**, with per-protein MW and abundance.

Neither value is in it, by any obvious recipe:

| recipe | result | vs 46429.8 |
|---|---|---|
| plain mean MW, 413 rows | 44897.97 | −1531.8 |
| abundance-weighted mean | 42850.42 | −3579.4 |
| `used for quantification == 3` subset | 48252.73 | +1822.9 |
| row count implying mean 46429.8 | 399.37 | not an integer |

The chain between the two entries *is* confirmed exactly: 107 g/L ÷ 46429.8
g/mol = 2.305 mM, the recorded value of 108346 to four figures.

Positive controls fire on the same files (the paper's stated `413`, and depth
`9.57` in the other paper's DataSheet), so the reader works and the absence is
real. **Reaching the data is not the same as confirming the number**, and this is
a worked example of an entry that is reachable, readable, and still
unconfirmable without knowing the curator's recipe.
