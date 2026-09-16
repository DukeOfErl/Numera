# Judged faithfulness

## Why

`add-answer-evaluation` built the deterministic layer and the records it reads. The judged layer —
a model separating an answer into claims and judging each against the context the agent was shown —
was group 6 of that change and is deferred here, for a reason measured rather than assumed.

**ADR-0510 requires a judge to be gated on measured agreement with the deterministic scoring, against
a golden set, before any judged figure is trusted.** The golden set was built: 30 answers from the
2026-09-11 baseline, read and labelled by hand. It came back **29 sound, 1 unsound, 0 unclear**. A
judge that answered "faithful" to everything would agree 97% of the time, so agreement measured
against this reference is a high number that means nothing, and no floor can be set from it.

That is a fact about the instrument, not about the answers. It says the reference cannot discriminate
here — and building the judge against it would produce exactly the shape ADR-0510 exists to prevent:
a validated-looking figure resting on a validation that could not fail.

The second reason is where the defects actually were. Every fault found in that baseline came from
the deterministic layer or from reading answers by hand: a citation swap (a correct number under a
wrong identifier), two answers claiming the corpus holds less than it does, and — twice — expected
lists built by a method that missed a third of what it should have found. None of those is what a
faithfulness judge catches, and one of them, the citation swap, is a case a faithfulness judge will
very likely pass, because the number *is* in the context.

So the judged layer needs a reference that can fail before it is worth building, and that is a work
package of its own rather than the tail of another.

## What changes

- A judge wrapper over the project's model, and a `judge` pass that reads a results file and writes
  judgements to a second file, keyed by question, repeat and judge model.
- A discriminating reference **first**: a question set or a set of answers containing faults a
  faithfulness judge should catch, so agreement is measurable in both directions.
- The judged figures in the report, beside the deterministic ones and never combined.
- The `deepeval` dependency, which moves here with the layer that uses it.

## What does not change

The deterministic evaluation, which needs none of this. `add-answer-evaluation` ships the harness,
the question set, the records and every score that needs no model; a deterministic run is unaffected
by whether this change is ever built.

## Open questions

- **How to build a reference that can fail.** Harder questions, a set seeded with answers wrong in
  ways faithfulness can see, or answers from a weaker model. Each costs a run and a labelling
  session, and each measures something slightly different.
- **Whether DeepEval is still the right vehicle.** ADR-0500 chose it, and its faithfulness metric was
  measured against the installed version. That decision is not reopened here, but the vendor's own
  prescribed workflow conflicts with decisions already made (see `add-answer-evaluation`'s design),
  so the parts of it adopted should be named explicitly.
