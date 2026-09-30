# ADR-1210: The door shows only real answers, verbatim, and no chart the model drew

- **Status:** accepted
- **Date:** 2026-09-30
- **Pull request:** _pending — `feat/door-demo`_

## Context

A visitor who has not signed in cannot find out what the app does, so the sign-in
door plays examples: a question typed out, an answer streamed back. The cheapest
examples are written by hand. They would show whatever the author thinks the agent
does, which is a promise about the agent that nothing checks.

Three examples were asked for on 2026-09-30. Two were run live against the
current corpus (`~/bionumbers/bionumbers.jsonl`, 14,294 entries) with
`anthropic/claude-opus-4.7`, and the answers were checked against the corpus:

- **Ribosomes in E. coli vs budding yeast.** Clean: 8 tool calls, $0.09, every
  figure cited. One flaw left as recorded: it says yeast has "3–10×" more
  ribosomes, where its own figures give about 3–30×.
- **mRNA-related entries per organism, as a text histogram.** $0.63, at the
  question ceiling. The agent has no counting tool; it rebuilt the counts from nine
  capped searches and got the largest bars wrong. It said human 53 (the corpus has 45)
  and E. coli 68 (73), outside the ±1–2 it admitted to, and it printed its working
  into the answer.
- **The spread of E. coli mRNA half-lives, as a text histogram.** $0.16, and honest
  prose: the corpus holds summary figures, not per-gene values. But the chart was
  wrong. Measured against its own minute axis, every bar sits about five minutes
  right of its value; 1.0 min is drawn at 6.2. It also found 4 of about 10 values,
  missing entries spelled "halflife" or "half life".

The second example was replaced with a saved evaluation answer (yeast vs E. coli
cell volume, ~60×, `opus47-x3-2026-09-17`, repeat 2).

## Decision

**Every example is a question actually put to the agent and the answer it actually
gave, verbatim.** It is labelled as recorded, with the model and the date, and
`door_demo.Scenario.source` names the run. The typed keystrokes may take words back
and retype them, but the text they end on must be the question asked, and a test
holds that.

**No example shows a chart the model drew.** The model cannot reliably place text
characters against a numeric axis, so a text chart in an answer is a formatting
request it satisfies with something that looks right. Rerunning until one lines up
would advertise a reliability the agent does not have. A distribution example waits
for a chart the *application* draws from numbers the agent returns. That is its own
work package, recorded in `docs/roadmap.md`.

## Trade-off accepted

The door shows two examples rather than three, and a small flaw in the first stays
visible because correcting it would make the example fictional. Adding an example
now costs a live run and a check against the corpus, not a sentence typed into
a file. That cost is the point.
