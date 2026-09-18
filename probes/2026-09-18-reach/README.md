# Reach probe — 2026-09-18: supplementary files and figure images

ADR-0040's **next probe #1**, the one it called "the only open question that
could still make the validator infeasible at useful scale". It asked whether the
~78% of entries whose value is not in the article text can be reached through
supplementary files and figure images.

**It cannot, and the reason is not the one expected.** `isOpenAccess` gates
supplementary material exactly as it gates article XML, so supplementary deepens
the reachable slice without widening it — and across a random sample of 250
entries, supplementary material moved **one**.

Read `FINDINGS.md` first. `METHOD.md` carries how the numbers were made and the
two wrong answers that came before them.

| File | Holds |
|---|---|
| `FINDINGS.md` | The six findings, with the tables |
| `METHOD.md` | Method, calibration, and the two wrong answers |
| `numfind.py` | Does a corpus value occur in this text? The surface-form generator and the short-form rule |
| `extract.py` | Reachable material → plain text: JATS XML, xlsx, docx, xls-as-XML. Names what it cannot read rather than returning empty |
| `calibrate.py` | **Run this first.** 4 canaries that must fail, 7 ground-truth cases that must pass. Aborts rather than print zeros |
| `gap_run.py` | The sample: resolve, fetch, classify |
| `gap_audit.py` | Both error directions on the result |
| `gap_backfill.py` | Fetches the supplementary side for entries that matched in the article — without it the audit is circular |
| `gap_clean.py` | Recomputes on the defensible subset |
| `fmt_census.py` | What the unreadable material actually is |
| `suppcheck.py` | The 108345/108346 worked example, with positive controls |
| `data/` | Results and logs. **Never committed** — see below |

## What may and may not be committed

`data/` is ignored by the repository's `data/` rule, verified with
`git check-ignore -v` before anything was written there. The per-entry results
carry corpus values and verbatim source context, so they are corpus derivatives
under ADR-0170.

The scripts and the two prose files are fine to commit: the tables in
`FINDINGS.md` are aggregate counts, and the handful of entries named
individually (108345, 108346, 115327, 117053) are cited as evidence.

The corpus itself is read from `/home/yoavpol/corpus/bionumbers.jsonl` and never
copied into the tree.

## Running it

Everything is stdlib except nothing — there are no third-party imports at all,
deliberately. `openpyxl` is absent from this project's environments and `.xlsx`
is a zip of XML, so `extract.py` reads it directly. That is a probe-scoped
choice, not a recommendation for production code.

    python calibrate.py                 # MUST pass before anything else is believed
    GAP_N=250 python gap_run.py
    python gap_backfill.py
    python gap_clean.py data/gap_results_backfilled.jsonl
    python fmt_census.py

`calibrate.py` reads the article XML cached by the 2026-09-09 probe under
`../2026-09-09-retrieval/data/`. That directory is ignored too; the curl loop in
that probe's README re-fetches it.

## The canary, and the flaw it caught

Same rule as the previous probe: a verification tool must prove it can fail
before you believe it passed. Here it was not ceremony — **the canary caught a
fatal flaw on its first run**, one that no calibration case would have found.

The finder generated rescaled *and* rounded surface forms, so the value `19043`
produced the form `"19"` and `87654321` produced `"88"`. Both match in any paper,
so everything would have been reported present.

| # | Input | Required | Observed |
|---|---|---|---|
| 1 | 19043 in PMC2680341 (one digit off a real value) | absent | absent |
| 2 | 87654321 in PMC2680341 | absent | absent |
| 3 | 66 minutes in PMC2288635 (paper states 65) | absent | absent |
| 4 | 33.7 %DW in PMC5720811 (a paper full of percentages) | absent | absent |
| 5–11 | the six 2026-09-09 entries, seven values | per `GROUND-TRUTH.md` | 7/7 agree |

Canaries 3 and 4 were added *after* the first failure, to exercise the
unit-confirmed path rather than only the plain-digit one — a negative case has to
differ from the positive one in the dimension the rule actually reads.

## What comes next

From `FINDINGS.md` §4, the capability ordering is now data-driven rather than
assumed:

1. **Figure images** — present in 41 of 46 reachable papers.
2. **PDF text** — 16 of 46.
3. **Binary `.xls`** — 5 of 46.

And two questions this probe opened rather than closed: the `no_pmcid` class is
**54% of the corpus sample** and was not investigated at all — some of those
references may resolve by DOI or title — and the figure arm still needs agents
that have not read the article, for the reason in `FINDINGS.md` §5.
