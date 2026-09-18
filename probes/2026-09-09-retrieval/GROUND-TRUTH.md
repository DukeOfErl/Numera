# Ground truth — the six entries

Six corpus entries, all carrying a `reference_pubmed_id`, all with an
open-access source. Quoted here as evidence for ADR-0040; a handful of entries
is citation, not corpus.

| BNID | Property | Corpus value | Source | In the source? |
|---|---|---|---|---|
| 105447 | Number of protein-coding genes, human | 19042 (unitless) | PMC2680341 | **Yes** — abstract, stated 3x |
| 115327 | Cell-specific carbon density, Landsort Deep | 200 / 1000 / 600 fg C/um^3 | PMC5005352 | **Yes** — p.7, one fused sentence |
| 109252 | Length of S phase, E. coli | "~55 to 65" min | PMC2288635 | **Partly** — see below |
| 108345 | Average protein MW, M. pneumoniae | 46429.8 g/mole | PMC3159969 | **No** — curator arithmetic |
| 108346 | Molar protein concentration, M. pneumoniae | 2.305 mM | PMC3159969 | **No** — curator arithmetic |
| 114567 | Carbohydrates, Synechocystis PCC 6803 | 28.4 (16.4-40.4) % DW | PMC5720811 | **Partly** — see below |

## The one place the answer key was wrong

**BNID 114567.** Recorded as unstated, on the strength of the curator's own note
("Calculated from the measured data, not shown in the pape[r]"). That is true of
28.4 and of 16.4 — neither string occurs in the paper — but **not** of the upper
bound. The paper states "up to c. 40% of dry weight" and `range_high` is 40.4.
The agent found the stated form and corroborated it (3011/7443 = 40.5%) from
per-cell numbers, and was marked wrong against a key that was wrong.

The general lesson, which is the finding most likely to sink a rate
measurement: **an entry can be partly grounded** — here one stated endpoint and
two curator-computed numbers, presented as a single value plus range. A key
that only admits grounded/ungrounded will mark correct answers wrong, and the
cost is curator time, not compute.

The same paper carries two decoys, both correctly refused by the agent and both
verified present: "up to c. 13%" (ref 31, Touloupakis 2015) and "11.1+-0.3%"
glycogen (ref 28) — prior studies, other substrains.

## The fused range

**BNID 109252.** The paper states 65 min. The `~55` is the authors' *earlier
published* estimate (Wang 2005, liquid culture) for different growth
conditions. The corpus range fuses two studies into one interval and says so
nowhere. The agent found 65 min verbatim and identified the ~55 as the authors'
prior work unprompted.

## The two curator computations

**BNID 108345 and 108346** rest on the same paper, whose every quantitative
table is Supplementary S1-S8 and therefore absent from the XML. Neither value
is stated. Both are the curator's arithmetic — 108346 being 107 g/L divided by
the 46429.8 g/mole of 108345, itself computed over supplementary data.

Two of the derivation's inputs *are* verbatim in the source and were used by the
agent: "413 different proteins ... covering 60% of all p[roteins]" and "167
copies per cell". The 3.2 GDa total does not appear as that string and is itself
a restatement.

That 60% is what makes 108346 interesting: the derivation assumes the 413
quantified proteins are the whole proteome when the paper says they cover 60% of
ORFs, so the derived figure is a **floor**. The agent said so. The corpus
records 2.305 mM to four significant figures with no uncertainty at all.
