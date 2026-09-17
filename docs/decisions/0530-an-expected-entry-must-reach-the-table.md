# ADR-0530: An expected entry must reach the table, not the prose

- **Status:** accepted
- **Date:** 2026-09-11
- **Pull request:** _pending — feat/eval-baseline_

## Context

`expected_entries` is a list of entry identifiers per question, and `citation_score` derives four
figures from it. Reading them together shows they do not agree on what the list means:

| Figure | Treats the list as |
|---|---|
| `all_expected_cited` | entries the answer **must** cite, all of them |
| `passed_over` — expected ∩ retrieved − cited | the same: not citing one is "a failure of selection" |
| `never_retrieved` — expected − retrieved | the same: "a failure of search" |
| `unexpected` — cited − expected | a floor, not a ceiling: *"reported, never counted as an error"* |

Three of those are required-set semantics and the fourth is admissible-set semantics, in one field.

The smoke run of 2026-09-07 then found the lists too narrow. `property` is free text, not a
controlled vocabulary — `resolve_property("Nuclear volume")` alone returns 14 spellings — and each
list had been built by searching one of them. For `yeast-nuclear-volume` the list held 3 entries
where 9 of the 52 nucleus-mentioning yeast entries record a nuclear volume in volume units. Task
5.3's notes recorded the remedy as widening the lists from the corpus vocabulary.

**Widening alone would have made the scoring worse.** Under required-set semantics
`all_expected_cited` becomes unreachable — a good answer to "what is the volume of a yeast nucleus"
does not cite nine entries — and `passed_over` fills with every entry the answer sensibly declined,
each labelled a failure of selection. The narrowness costs nothing today, because its only effect is
on `unexpected`, which is already not counted. So the recorded remedy moved the one figure that was
not hurting and broke two that were sound: the classic both-directions mistake, made while looking
only at the direction intended.

What the widening is nevertheless right about: those 14 spellings all mean the same property, and a
set that lists one of them is not describing the corpus. The error was in what the widened list was
then asked to prove, not in widening.

The rest of the material was already in place. `rows_for` returns cited entries first and then
**every other retrieved entry**, ranked by how close its wording is to the question — so the table a
reader sees is the retrieval set, ordered. Where a driver cuts it is a driver's business:
`TERMINAL_ROWS` is 5 in the CLI and the web's cut differs.

## Decision

**The expected set is every entry recording the asked property, whatever its spelling, and an
expected entry discharges its obligation by reaching the table.**

1. **Widen `expected_entries`** to every corpus entry recording the same property for the asked
   organism, across spellings. Built from the corpus vocabulary and never from what the agent
   cited — widening a set to what the system found makes it a set the system passes by construction.

2. **The headline pass/fail is `all_expected_reached_the_table`** — expected ⊆ retrieved, which is
   `never_retrieved` being empty. `rows_for` shows every retrieved entry, so this is exactly "did the
   reader get shown it". The prose figure survives beside it as a secondary, because prose citation
   is what a reader actually follows.

3. **Rank is a second, continuous figure**: the position of each expected entry in `rows_for` order.
   "Reached the table" would pass an entry ranked fortieth, which is invisible in practice. A search
   failure and a ranking failure are different defects with different fixes, and one number would
   hide which is happening.

4. **Driver truncation is not scored.** Scoring against a display cut would make the same answer
   score differently depending on who asked, which is what ADR-0110 exists to prevent.

5. **`admissible_entries` is a new, separate list**: a *different* property that still answers the
   question — the nucleoid for "the nucleus of a bacterium", cell width for "cell diameter" in a rod.
   Citing one is not an error and not citing one is not a failure; its job is to make `unexpected`
   mean something, so that a citation outside both lists is genuinely off-topic. It is hand-written
   per question, because no derivation produces it: once the expected set covers every spelling of
   the asked property, a vocabulary-derived set *is* the expected set.

6. **`passed_over` is not a failure and is not judged as one.** Under a widened expected set a good
   answer cites four of nine and the table carries the rest. The question worth a judge is whether
   *omitting* an entry changed the answer — an unmentioned growth condition, a value an order of
   magnitude from everything cited — and it is gated behind a deterministic check on the spread
   between cited and passed-over values, so the judge is paid only where the numbers differ. That
   gate is the comparison ADR-0520 needs rebuilt anyway; they share one implementation.

**`admissible_entries` is read from the question set at report time and is not copied into the
result record**, unlike `expected_entries`. Borderline cases are found by reading answers, which is
task 5.4 and happens after the run.

Rejected: relaxing the pass to "cited at least one expected entry". It scores a one-of-nine answer
and a nine-of-nine answer alike, and says nothing at all about whether the search found them.

## Trade-off accepted

**Two lists in one file now behave differently, and that is a wart.** `expected_entries` freezes
into every result record; `admissible_entries` does not. The reason is that one is settled before a
run and the other is discovered by reading the run's answers, and freezing the second would mean
paying for a fresh run after every borderline case found. A reader of the question set has to know
which is which, and nothing about the file's shape tells them.

**The widened lists must be right before the baseline.** `expected_entries` is copied into each
record at run time, so a set fixed afterwards does not repair the records it was scored into — the
only remedy is re-asking at cost. Everything else here is recomputable from raw material: the rank
figure, the admissible classification and the judged omission check all read the question set and
the corpus at report time, so getting them wrong is cheap. This is the whole reason the widening
leads and the rest follows.

**The rank figure couples an evaluation number to a presentation heuristic.** `_relevance` is
`entries_table`'s own wording-overlap score, tuned for a reader. Improving it will move an eval
figure that no answer changed. Accepted because the alternative — ranking the eval's own way —
measures something no reader ever sees.

**"The same property, whatever the spelling" is a hand judgement, once per question.** There is no
controlled vocabulary to make it mechanical, which is why the corpus has 14 spellings of one
property in the first place. Each widened list is therefore a claim by its author, and a wrong one
is invisible until someone reads an answer against it — which is what task 5.6 asks a reviewer to
do with the set rather than only the code.
