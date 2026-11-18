# Three models, three repeats, 2026-09-17

Ten questions, three repeats, against corpus `a3364acbfa69fe90` (14,294 entries), prompt
`f8c6e7484a570bab`, code `git 8d15303`. **90 results, $3.58, no failures.** Results live in
`evaluations/`, which is gitignored: every result carries the retrieval results verbatim, so a
results file holds corpus text (ADR-0170).

Run because the comparison on the morning of the same day — **one** repeat each — had Haiku and
Opus one point apart and was read as a tie. It was noise.

> **Re-scored 2026-09-22.** The figures below are against the expected lists as they read on
> the day of the run. Four entries have since joined them, and every figure here falls one or
> two points as a result: see `docs/evaluations/2026-09-22-expected-list-triage.md` for the
> re-scored table. No conclusion in this note changes.

## What it says

| Figure | Haiku 4.5 | Opus 4.7 | MiniMax M2.7 |
|---|---:|---:|---:|
| Expected entries reaching the table | 176 of 333 (53%) | **218 of 333 (65%)** | 31 of 333 (9%) |
| — `basic` | **132 of 189 (70%)** | 128 of 189 (68%) | 23 of 189 (12%) |
| — `compound` | 44 of 144 (31%) | **90 of 144 (62%)** | 8 of 144 (6%) |
| Results where every expected entry reached it | 8 of 21 | 6 of 21 | 0 of 21 |
| …and cited in the prose | 89 (27%) | **138 (41%)** | 11 (3%) |
| Cited, in neither list | 4 | **24** | 1 |
| Deepest expected entry in the table | median 17, worst 46 | median 9, worst 91 | median 4, worst 15 |
| Unsupported questions declined | **4 of 6** | 6 of 6 | 6 of 6 |
| Retrievals per question | 6.0 | 6.2 | 9.6 |
| Cost over 30 questions | $0.40 | $2.89 | $0.29 |
| Endings | answered 30 | answered 30 | retrieval_bound 18, answered 12 |

## The gain is entirely in the compound questions

On `basic` questions — one property, one organism, retrieved rather than deduced — the two Claude
models are a tie: 70% against 68%, which three repeats cannot separate. The whole of Opus's
twelve-point lead is `compound`: 62% against 31%.

So the choice of model is a decision about multi-organism comparisons and calculations, and buys
nothing on lookups. This is what the tier was added for. Without it the headline figure would have
read as a uniform improvement worth seven times the price, and the honest reading is narrower.

One figure cuts the other way, and it is not a rounding artefact: Opus finishes fewer `basic`
questions completely — every expected entry reached the table in 2 of 12 results, against Haiku's
6 of 12 — while matching it on the total. It spreads a similar number of retrievals over more
distinct entries rather than exhausting the one property it was asked about.

## The finding that is about correctness rather than coverage

**Haiku declined only 4 of the 6 unsupported questions.** Twice it answered `planarian-cell-volume`
with prose stating a quantity; both repeats are flagged by the stated-quantity rule and named in the
report. Opus and MiniMax declined all six.

The unsupported questions exist to check that the agent says the corpus does not hold something
rather than reaching for whatever is adjacent. A model that answers them is failing at the thing
this app is for, and the failure does not appear anywhere in the reach figures.

## What is not settled

- **Run-to-run variance is large.** Different entries are cited across repeats on 7 of 10 questions
  (Haiku) and 8 of 10 (Opus). Three repeats is the floor for reading any of this, not comfort — and
  the one-repeat run this replaces is the standing demonstration.
- **Opus cited 24 entries in neither the expected nor the admissible list**, against Haiku's 4. The
  last time that number rose, it was the signal that the expected lists were too narrow, and
  hand-triage turned 24 expected entries into 111. Until those 24 are triaged, 65% is a floor
  reported against a list that may still be wrong, not a ceiling.
- **MiniMax M2.7 was not measured so much as observed to fail**: 18 of 30 results ended at the
  retrieval bound and 20 reached the model-call bound. Whether that is the model or the prompt is
  untested, and nothing here distinguishes them.
- The MiniMax group carries `code git 8d15303+modified` and a $0.90 question ceiling rather than
  $0.60 — an uncommitted edit to the defaults landed between the Opus and MiniMax runs. It changes
  nothing measured here: no result in any of the three groups reached a spend ceiling.

## What it changed

The default model had already moved to Opus 4.7 before these runs, on the grounds that the one-repeat
comparison could not tell the two apart and the figure did not measure the prose. That reasoning is
now superseded rather than contradicted: there **is** a measured difference, it is twelve points, and
it is confined to the compound questions. `config.py` and the changelog say so.
