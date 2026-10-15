# ADR-0980: What a reviewer may choose, and a model may not

- **Status:** accepted
- **Date:** 2026-10-09
- **Pull request:** not yet opened — branch `feat/simulated-review`

## Context

The review pool now spans four harvest domains (biology, organismal, biophysics, chemistry,
physics) and papers from several groups' topics. Yoav asked on 2026-10-09 for two things on the
review page: a way to change paper when the reviewer does not feel at home in the topic, and a
way to choose a domain or topic; and that "this should only be available to the human reviewer,
not the AI".

Three questions. **Where the choice lives**: in the page alone (the serving query stays as it
was and the page filters what it gets — a page that pages through items to find one is a page
that silently loads text nobody asked for) or as arguments to the serving query (chosen). **What
a skip is**: dropped, so the paper is simply never shown to that reviewer (no trace that a paper
was refused), or recorded with who and when (chosen — a paper nobody wanted to review is a fact
about the pool). **Where the domain comes from**: parsed out of each paper's fingerprint JSON at
query time (spelled differently on SQLite and Postgres), or carried as a column filled on load
from the harvest scope, with runs from before scopes read as biology (chosen); the topic is a
column the harvester fills (`Paper.topic`, `feat/harvest-prototype`), empty until it does.

## Decision

`review_paper` gains `domain` and `topic`; `review_skip` records a reviewer's skipped papers.
`store.Preference(domain, topic)` is a person's choice and is passed by the page to `next_item`
and `remaining`; with one, the papers the reviewer skipped are left out too. `undecided_items`,
the simulated review's reader, takes no preference, and the runner never builds one: a model
reviews its assigned subset whatever a person set aside. The page offers the domains and topics
the loaded papers actually carry, and a "Skip this paper" button beside the citation.

## Trade-off accepted

A person's view of the pool and a model's now differ, by design: coverage figures for human
roles will reflect choices, and the dashboards must say so where they compare roles. A skipped
paper is not a decision and counts toward no tier; it is a row for the operator. Two more
columns the loader fills from the records (`Fingerprint.scope`, `Paper.topic`), and one more table in a store that already has four.
