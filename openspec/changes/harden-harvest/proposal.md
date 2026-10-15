## Why

The 2026-10-07 code review of `add-harvest-prototype` left four findings open, deferred past the
2026-10-17 presentation so that change could close. None changes what the demo shows, but the
harvest is about to be run again over papers it has already read, and two of them decide what a
reader is told when that happens.

## What Changes

- The twenty-entry bound per article is enforced, not only asked for: entries beyond it are
  dropped before any further spend, and the drop is recorded.
- Readings of one article from different runs are linked: a reviewer is served them together, and
  an entry says that its article was read more than once and where the readings differ.
- A list of articles treats a line whose first non-blank character is `#` as a comment.
- The review page keeps one database connection across reruns whichever way its database is named
  (no behaviour change; listed for the task).
- The guard refusing a run folder git would track lives in the operation that writes the run, once.
- Nine findings of the 2026-10-15 code review that let no wrong value through: a re-fetched paper's
  licence, superscript citations, spanned row labels, a re-extracted run mixing on load, Markdown on
  the review page, condition quotes in rendered form, second-text fragments, the model id's default,
  and two duplicated tables.

Builds on `add-harvest-prototype` (tasks 6.5, 6.6, 6.8, 6.9 there, moved here on 2026-10-15). The
short citation labels of `add-ask-over-store` (`PMC…-n`, `-n.2` for a later run) are that
change's; the link between readings here is what makes `-n.2` explainable to a reader.

## Capabilities

### New Capabilities

### Modified Capabilities
- `number-harvest`: the twenty-entry bound is enforced and recorded; comment lines in a list of
  articles.
- `review-task`: readings of one article from different runs are served together and linked.

## Impact

- `src/bionumbers/extraction.py` (the bound), `cli.py` (comment lines, the run-path guard),
  `store.py` and `review.py` (serving and linking across runs), the review page's engine.
- The store gains whatever records the link between readings; additive, as every store change on
  this prototype has been.
- ADRs from the block `1700`–`1740`, reserved in `CLAUDE.md`.
