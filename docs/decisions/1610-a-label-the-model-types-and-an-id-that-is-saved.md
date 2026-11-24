# ADR-1610: A harvested value has a label the model types and an id that is saved

- **Status:** accepted
- **Date:** 2026-10-15
- **Pull request:** not yet opened — branch `feat/ask-over-store` (`add-ask-over-store`)
- **Amended 2026-11-24** (`fix/store-label-order`): runs are ordered by each run's first row in
  SQLite's insertion order (`rowid`), not by `review_item.created_at`. `created_at` is the wall
  clock at load, and a clock stepping back between two loads put the later run first and moved
  every earlier label (`PMC1000001-2` became `PMC1000001-2.2`), which made five tests flaky and could
  have made a saved citation name another value. `tests/test_store_corpus.py` reproduces it with a
  clock that steps back on every reading. Measured on the review store that day: no paper has more
  than one run, so no existing label moved.

## Context

Every entry the ask agent cites until now was a BioNumbers entry, named by its BNID: a short
integer that the model types, the parser reads, the trail saves, and that never changes. A value
harvested from a paper has no such number. The store names it by `review_item.item_id`, which is
`{run_id}-{pmcid}-{n}-item` — for example `compare-gpt-6.1-sol-2026-10-03-PMC2652108-1-item`.
That id never changes and names one value forever: the store is insert-only, and extracting a paper
again is a new run with new ids.

Options considered:

1. **The model cites the item id.** One identifier for everything, and stable. But it is about 50
   characters and names the run and the model that extracted the value, which the user rejected for
   what a reader sees. Models also copy long ids unreliably, and each miscopy is a citation of
   nothing. The seeding session proposed this on 2026-10-15 and withdrew it for option 4.
2. **Synthetic integers in a range BNIDs do not use.** No change to how citations are read. But a
   reader cannot tell a harvested value from a BNID, and the user preferred the PMCID form.
3. **`PMCID-n` as the only id, refusing to load a duplicate.** Short and readable, but `n` is the
   value's number within one extraction, so the first time a paper is extracted again the app
   stops loading.
4. **Two identifiers with different jobs**: a short label the model types, and the item id that is
   saved.

## Decision

Option 4.

- **The label** is `PMCID-n` (`PMC2652108-1`), cited as `[[PMC2652108-1]]`. When a paper has been
  extracted more than once, the extraction loaded first keeps bare labels and the k-th is suffixed
  `.k` (`PMC2652108-1.2`), runs ordered by when they were loaded into the store
  (the first row's `rowid`; `review_item.created_at` until the amendment above). The store is insert-only, so an existing label never moves. Each
  extraction's values stay separate entries; none is merged or dropped. A duplicate label after that rule stops the load.
  The citation parser recognises exactly this shape (`citations.LABEL`), and the loader checks every
  label it makes against the same pattern.
- **The saved id** is the item id. `Entry.record_id` returns it, and every record that is saved —
  the trail's `search` and `entry.retrieved` rows and the question-and-answer record
  `answer.evidence` — carries it beside the label. A corpus-file entry's BNID is both, so those
  records are unchanged for it.
- **A label is never resolved again.** Load order is stable while the store is only added to, but a
  store rebuilt by loading its runs in another order would relabel them. Ordering by the date a run
  was made — the first draft — would have relabelled on any restore or backfill of an older run.
  Either way it is harmless only because nothing saved is ever looked up by its label. Anything
  that reads old answers — a view of past citations, a trail replay, an evaluation over old
  results — resolves by the saved id.

`bionumbers.label` names only an integer a BNID; a label is shown as itself.

## Trade-off accepted

Two identifiers where there was one, and a rule — never resolve a saved label — that nothing in the
type system enforces. Accepted because the alternatives each give up something the user asked for:
readable citations (option 1), telling the sources apart (option 2), or surviving a re-extraction
(option 3). The rule is written where a future change would be made: the docstring of
`Entry.record_id`, and design D3 of `add-ask-over-store`.
