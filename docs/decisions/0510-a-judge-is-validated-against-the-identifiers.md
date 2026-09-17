# ADR-0510: A judge is validated against the identifier scoring, never the reverse

- **Status:** accepted
- **Date:** 2026-09-03
- **Pull request:** _pending — feat/answer-evaluation_

## Context

The evaluation has two scoring layers. The first compares the entry identifiers an answer cited
with those the question set expects, and scores whether an unsupported question was declined. It
is exact, cheap, and blind to a right citation beside a wrong number. The second asks a model to
separate the answer into claims and judge each against the context the agent was shown. It sees
what the first cannot, and it is a model: `add-ask-agent`'s proposal recorded, from independent
measurements, that judge verdicts flip under simple pushback in a quarter to two thirds of cases,
and required that adoption "be gated on agreement with the deterministic scoring already in place
— a correlation floor against a golden set — rather than assumed after it".

Three shapes were possible: one combined score with the judge weighted in; the judge as the
primary instrument with identifiers as a sanity check; or two figures kept apart, with the judge
earning trust against the first.

## Decision

Two layers, structurally apart. Records hold the deterministic result; judgements go to a second
file, keyed by question, repeat and judge model, written by a separate pass that can be re-run for
judge spend only. The report shows the judged figures beside the deterministic ones and never
combines them into one number.

The judge is validated against the identifier layer on every result where both can speak: a
fabrication — a quantity given for an unsupported question — must be judged unfaithful, and a
judged-faithful fabrication is reported as a judge miss. Where the identifier layer is satisfied
and the judge finds a claim unsupported, that is the judge adding information, listed with the
claim and reason rather than counted against it. Below a configured agreement floor every judged
figure carries an unvalidated mark. The deterministic harness is built and its baseline recorded
before the judge is run at all.

## Trade-off accepted

Two figures are harder to read than one, and a reader wanting a single number will not get it. A
judge miss is defined by the deterministic layer, so a fabrication the two-signal quantity rule
fails to flag cannot be counted as a miss either — the rule is deliberately tuned to over-flag so
that gap is small, and the report lists every flagged decline so the over-flagging is visible. The
agreement floor's first value is a placeholder until a judged baseline exists, and is recorded as an
open question rather than dressed as a measurement.
