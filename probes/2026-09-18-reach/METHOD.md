# Method — reach probe, 2026-09-18

How the numbers in `FINDINGS.md` were produced, and the two wrong answers that
came first. Both were wrong in the flattering direction, which is the reason
this file exists.

## The finder, and why it is calibrated rather than trusted

`numfind.py` asks whether a corpus value occurs in a body of text. ADR-0040
records that a string-level pre-classification was **attempted and discarded as
unreliable**, on two named false negatives — `19,042` (thousands comma) and
`46.4298 kDa` (unit-prefix form) — so reviving the idea needs an argument.

The argument is that the job is different. ADR-0040 wanted a *pre-filter
deciding which entries to probe*, where a false negative silently removes a case
from the experiment. Here it produces a *population count whose error is
measured*, and both named failure modes are generated as surface forms
explicitly.

`calibrate.py` is what makes the count mean anything. It runs the finder against
the six 2026-09-09 entries — the only ground truth this project has — plus four
canaries that must **not** match. It aborts rather than print a table if a canary
fires.

    CANARIES (must all be ABSENT)      4/4 absent
    CALIBRATION CASES                  7/7 agree with ground truth

Every expectation in it is sourced from `GROUND-TRUTH.md`, not from running the
finder and recording what came out. An expectation read off the tool under test
is a photograph of current behaviour promoted to a contract.

### The canary earned its place immediately

The first version generated rescaled *and* rounded forms, so `19043` produced the
surface form `"19"` and `87654321` produced `"88"`. Both occur in any paper. The
canary caught it on the first run; no calibration case would have, because they
all happened to be correct for other reasons.

Two rules came out of that failure:

- **A rescaling is never combined with a rounding.** Each may drop digits;
  together they drop enough to match unrelated text. Rounding *alone* is safe
  even at 2 significant figures, because for a large number it pads zeros
  (`19043` → `19000`, still five digits) rather than shortening.
- **A form of fewer than three digits is only a hit when a unit token sits
  within 30 characters, and a one-digit form is never a hit at all.** `1000`
  rescaled to `"1"` is the same failure wearing a different hat.

A third fix came from calibration case 109252: the unit prefix was taken from the
*corpus* side at four characters, so `minutes` → `minu`, which matches nothing in
a paper that writes `min`. Three characters, because the paper is usually the one
using the shorter form.

### Which direction the finder is allowed to be wrong

A missed occurrence understates how often a value is stated in its source, which
understates reachability. A spurious occurrence overstates it and would make the
validator look feasible where it is not. The uncertainty is pushed into false
negatives deliberately, and the calibration is n = 7 — enough to catch a broken
finder, nowhere near enough to quote a false-negative rate. No figure in
`FINDINGS.md` should be read as precise.

## The sample

`gap_run.py`. Random sample, `seed = 20260918`, drawn from the 8,696 corpus
entries carrying both a `reference_pubmed_id` and a value or range endpoint.
n = 250. Each entry: resolve PMID → PMCID and `isOpenAccess` via the Europe PMC
lite search, then fetch article XML, then the supplementary bundle, and run the
finder over each in turn.

The corpus is read from `/home/yoavpol/corpus/bionumbers.jsonl` and never copied.
Per-entry results land in `data/`, which the repository's `data/` rule ignores:
they carry corpus values and verbatim source context, so they are corpus
derivatives under ADR-0170 and must not be committed.

## The two wrong answers

**First answer: a 43.8% recipe gap.** 21 of 48 reachable entries came back
`not_found`, and the temptation was to report that as "44% of reachable entries
cannot be confirmed from their source". The audit (`gap_audit.py`) found that 18
of those 21 papers carried files the text path could not open — binary `.xls`,
PDF, figure images, one paper with 280 unread files. `not_found` was largely
measuring unreadable formats, not absent numbers.

**Second answer: a 96% hit rate on "fully read" papers, and it was circular.**
Partitioning on "was everything readable" gave 26 `in_article`, 0
`in_supplement`, 1 `not_found` — an apparently clean 96%. The partition was an
artifact of the harness: `gap_run.py` only fetched a supplementary bundle **when
the article match had already failed**, so every `in_article` entry had no
supplementary statistics at all and passed the "fully read" test by default. The
partition separated found from not-found by construction and could not have
produced any other number.

`gap_backfill.py` fetches the missing side. With it, the genuinely fully-read set
is **4 papers**, not 27, and the recipe gap is not measurable from this sample at
all. That is finding 3 in `FINDINGS.md`, and it is a better answer than either of
the two that preceded it.

The general shape is worth keeping: **a covariate collected only on the failing
branch will partition the outcome perfectly, and the resulting table looks
clean.** Both wrong answers flattered the conclusion, and neither would have been
caught by rerunning the same code.

## Re-running

    python calibrate.py                  # must print 4/4 canaries absent, 7/7 cases
    GAP_N=250 python gap_run.py          # the sample; writes data/gap_results.jsonl
    python gap_backfill.py               # fills in the in_article side
    python gap_clean.py data/gap_results_backfilled.jsonl
    python fmt_census.py                 # what the unreadable material is
    python suppcheck.py                  # the 108345/108346 worked example

`calibrate.py` depends on the article XML cached by the 2026-09-09 probe in
`../2026-09-09-retrieval/data/`. That directory is ignored; re-fetch it with the
curl loop in that probe's `README.md` before calibrating.

## What this probe did not establish

- **No figure-reading rate.** One figure was read, by a reader who had already
  seen the sentence describing it. See `FINDINGS.md` §5.
- **No recipe-gap rate.** n = 4 fully-read papers.
- **No false-negative rate for the finder.** Calibration is n = 7.
- **Nothing about non-open-access papers** beyond that both endpoints return
  nothing for them, on a sample of 2.
- The `no_pmcid` class (54% of the sample) was not investigated. Some of those
  references may be resolvable by other means — a DOI, a title search — and that
  is untested.
