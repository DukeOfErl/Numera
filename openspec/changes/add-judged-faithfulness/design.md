# Design

## What is inherited, and what is not

`add-answer-evaluation` recorded findings this change depends on. They are not repeated here in full;
what follows is what a reader must know before writing code.

**The DeepEval surface, measured against the installed 4.2.1** (its design document has the detail):

- The faithfulness verdict is **three-valued** — `yes` / `no` / `idk` — not a boolean.
- `idk` counts as **faithful** by default; `penalize_ambiguous_claims=True` is what changes it, and
  the shipped default is lenient on exactly the claims the judge was least sure of.
- `_calculate_score` returns **1.0 for an empty verdict list**, so a refusal, or an answer whose
  claims the extractor cannot parse, reads as perfectly faithful. The gate is therefore *were claims
  extracted*, not *was the score high* — the same number, two different facts.
- `truths_extraction_limit` caps the truths drawn from context.
- `GEval` is the framework's answer for custom single-turn criteria, so deferred judged metrics
  become GEval criteria rather than hand-written rubrics.

**The vendor skill prescribes a different topology** — a pytest suite driven by `deepeval test run`
over goldens from `deepeval generate`, with results to Confident AI. Two of its defaults are already
refused: a generated golden set is one the system under test produced, and **a results file carries
corpus text verbatim**, so sending it to a hosted service is the leak `evaluation.py` refuses on disk
by another route (ADR-0170).

## The reference problem, which is this change's actual work

The 2026-09-11 labels are 29 sound of 30. Agreement against them is uninformative. Three ways to get
a reference that can fail, none free:

| Approach | Cost | Measures |
|---|---|---|
| Harder questions | a run + a labelling session | whether the judge sees faults in answers a good model still gets wrong |
| Seeded faults | hand-writing wrong answers | whether the judge catches known, planted defects — but planted faults are not the faults that occur |
| A weaker model's answers | a run + labelling | naturally occurring faults, at a higher rate |

The third is the most honest and the cheapest to label, because the faults are real. The second is the
only one that guarantees both directions are populated. They are not exclusive.

**One case is known to discriminate already** and should be in any reference: repeat 2 of
`yeast-nuclear-volume` in the baseline cites 101627 ("Restriction enzyme EcoRI catalytic rate") for
"2.83 μm³ during late anaphase", which is 105627 — a digit transposition. The number is right and is
in the retrieval context, from 105627, so **only the attribution is wrong**. A judge reading claims
against context will very likely pass it, and the deterministic layer already flags it as an
unretrieved citation. It is the one answer in thirty where the two layers should disagree.

## Judgements go to their own file

Keyed by question, repeat and judge model, written by a pass that can be re-run without re-asking.
That shape is ADR-0510's and is inherited. **It carries corpus text** — a judgement quotes the claim
and the context it was judged against — so it takes the same refusal every other artefact of a run
takes, and it is never sent to a hosted service.
