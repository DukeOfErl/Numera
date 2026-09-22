# Triaging the entries cited in neither list, 2026-09-22

Every result in `evaluations/` was swept for entries a model cited that appear in neither the expected
nor the admissible list of the question they were cited under. Five runs, 150 results: Haiku 4.5,
Opus 4.7 and MiniMax M2.7 from 2026-09-17, Nemotron 3 Ultra and 3.5 Lightning from 2026-09-21.

**22 distinct (question, entry) pairs.** Four moved to an expected list, fifteen to an admissible one,
and three were already accounted for. **No citation in any of the five runs now falls outside both
lists.**

## What moved, and why

**Four entries joined an expected list**, each one a genuine gap in the method that built the list:

| Entry | Question | Why it was missed |
|---|---|---|
| 117348 | `ecoli-ribosomes` | "Total ribosome number…", 26,100±4,020 ribosomes/cell — a fifth spelling the wording sweep did not carry, and its units are `N/A` because the figure sits in `range_raw`, so the unit sweep could not have found it either |
| 107946 | `yeast-cell-volume-conditions` | Effect of carbon source on volume at bud initiation |
| 107947 | `yeast-cell-volume-conditions` | Effect of nitrogen source on growth rate and volume at bud initiation |
| 107949 | `yeast-cell-volume-conditions` | Effect of growth rate on mean volumes under glucose or NH4+ limitation |

The three yeast entries share a shape and a cause. Each records exactly the dependence the question
asks for, and each carries `units: N/A` with no scalar because its figures live in a linked table.
The list was rebuilt on 2026-09-16 by a unit sweep — **and a sweep over units finds nothing whose
units are absent.** The note on that question already records the wording sweep missing `100490`; this
is the same failure one method later.

**Fifteen entries became admissible.** Most were already the subject of an explicit exclusion and only
needed saying: the three E. coli organelle volumes the cell-volume sweep set aside (100011, 100012,
100013), the six exponential-phase ribosome counts a stationary-phase follow-up contrasts against, and
four linear sizes on the rule `yeast-vs-ecoli-volume` already states. Full reasons are in each
question's `notes`.

**Uncertainty went to `admissible` on purpose.** The two lists cost different things: an entry wrongly
made admissible silences one reported line, while an entry wrongly made expected becomes a miss for
every model in every run, forever. So an entry moved to expected only where it plainly records the
asked property for the asked organism, and everything defensible-but-not-that went to admissible.

## Both directions, measured

Re-scored with `--expected-from-set`. The left column is what each note reported; the right is the
same results against the lists as they now read.

| Run | Before | After | `basic` | `compound` | Cited in neither |
|---|---:|---:|---:|---:|---:|
| Opus 4.7 | 218 of 333 (65%) | 221 of 345 (**64%**) | 65% | 62% | 24 → **0** |
| Nemotron 3 Ultra | 203 of 333 (61%) | 206 of 345 (**60%**) | 61% | 58% | 13 → **0** |
| Haiku 4.5 | 176 of 333 (53%) | 177 of 345 (**51%**) | 66% | 31% | 4 → **0** |
| Nemotron 3.5 Lightning | 118 of 333 (35%) | 118 of 345 (**34%**) | 46% | 18% | 8 → **0** |
| MiniMax M2.7 | 31 of 333 (9%) | 31 of 345 (**9%**) | 11% | 6% | 1 → **0** |

**Every model lost ground, and none of the conclusions moved.** The denominator grew by twelve slots
(four entries × three repeats) and the numerators by at most three, so each figure falls one or two
points. The ordering is unchanged, all twelve added slots are `basic`, and the `compound` column —
the one the model choice actually turns on — is untouched: Opus 62%, Ultra 58%.

## The finding worth more than the numbers

Who reached the four newly-expected entries, out of three repeats each:

| Entry | Haiku | Opus | MiniMax | Ultra | Lightning |
|---|---:|---:|---:|---:|---:|
| 117348 | 0 | **3** | 0 | 0 | 0 |
| 107946 | 0 | 0 | 0 | 1 | 0 |
| 107947 | 0 | 0 | 0 | 1 | 0 |
| 107949 | 1 | 0 | 0 | 1 | 0 |

**Five models over fifteen runs reached these four entries seven times out of sixty.** They are not
hard questions — they are the most on-point entries in the corpus for what was asked. What they have
in common is their shape: no scalar, `units: N/A`, the number in `range_raw` or behind a table link.

`search_entries` returns one row per entry as `entry_id, property, organism, value units`. For an
entry of this shape the value and units are **empty**, so the model sees a row that looks like it
carries no number and moves on. The corpus holds the figure; the retrieval surface does not show it.

That is a defect in what the tool returns, not in any model, and it is invisible to every figure in
every run above — the entries simply never appear. It wants its own change, and none of these
evaluations should be read as measuring it.

## What this does not settle

- **Triage is complete for these five runs only.** A new model citing a new entry re-opens it; the
  sweep is cheap to re-run and should be, after any run against a new model.
- **The corrected lists are still swept lists.** Two sweeps have now each missed entries the other
  would have caught, and this triage found a third class neither could see. The lists are better than
  they were, not known to be right.
- **Nothing was re-asked.** The expected list is never shown to the agent, so no answer could have
  changed; that is what makes `--expected-from-set` legitimate here.
