# ADR-1220: The door shows shortened answers, titled "Demo"

- **Status:** accepted; amends ADR-1210
- **Date:** 2026-10-01
- **Pull request:** _pending — `feat/door-demo`_

## Context

ADR-1210 put verbatim answers on the door, each labelled "Recorded example · a real
answer from <model>, <date>". Yoav looked at it and found three problems. The
answers were too long to read in the frame, the label was clutter, and the pause
between examples was long enough that a visitor thought the demo had stopped.

He asked for specific cuts, for one sentence to be reworded, and for a "Demo" title
above the frame instead of the label. The reworded sentence originally kept the
model's "~10–60×" next to an E. coli range. No E. coli range the answer cites gives
that ratio: against yeast's 26–74 μm³, the 1.5–4.4 μm³ range gives about 6–50×.
Yoav chose that range and the recomputed ratio.

## Decision

**An example may be shortened, and every edit is recorded beside it.** Each
scenario in `door_demo.json` carries an `edits` field. It names every cut, every
sentence reworded and by whom, and any figure recomputed with the arithmetic. A test
fails if the field is empty.

The edits stay inside these limits:

- **Every figure kept is one the corpus holds**, cited as the model cited it.
- **A computed figure is recomputed from the figures kept**, never carried over
  from text that no longer supports it.
- **The question is still the one asked**, and `typed` still holds the keystrokes to it.

**The page is titled "Demo" and names no model.** With shortened answers, "a real
answer from <model>" would claim more than the page shows. The provenance moves into
the data (`model`, `recorded`, `source`, `edits`), where it can be traced and is not
asserted to the visitor.

**The pause after an answer is 3.5 s**, down from 9. Pointing at the frame still
holds it for as long as the reader wants.

ADR-1210's refusal of a model-drawn chart stands unchanged.

**Revised the same day.** The heading became "What can SciNumbers do?", which
still presents the frame as a demonstration and names no model. Case 2 was then
rewritten from measured entries only, dropping the rule-of-thumb pair: typical yeast
42 μm³ against E. coli 1.1 μm³ (~40×), and a variability range over the measured
entries the answer cited (~6–170×). That is now more editor's text than model's,
which is the limit this ADR allows, not its norm: every entry is one the run cited,
and every figure is recomputed in the scenario's `edits`.

## Trade-off accepted

The door no longer promises that what it shows is exactly what the model said.
"Demo" is a weaker claim, and the honest one for an edited excerpt. Anyone checking
an example against its run has to read `edits` to see the difference. Ratio
sentences are the riskiest edits, because a hand-written sentence can carry a
computed claim the model never made; this one was checked against the corpus values
behind it.
