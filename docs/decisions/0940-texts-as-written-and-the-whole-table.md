# ADR-0940: A text is shown as the paper wrote it, and a cell brings its whole table

- **Status:** accepted
- **Date:** 2026-09-22
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

The first review screen bolded every number of the value inside the two texts, and showed a table
cell as its row and column headers plus the cell, deliberately not the table (the `review-task`
spec's original wording). Both came from the same worry: a reviewer reading a page of numbers loses
the one they are asked about.

Two things in the first live items said otherwise. The bolding pointed the reviewer at the answer
to the forced choice — a text that states the value lit up and one that merely mentions a number
did not — and it lit up unrelated digits too (every `1` in a value of `39 ± 1`, the review's finding
7). And Table 3 of PMC13118904, where eleven of the twelve live items came from, has a spanning
group header over concentration sub-headers and a control column: two header fragments do not tell
a reviewer which condition a cell belongs to, and the caption is where the paper says what the table
measures. Yoav asked for both changes on 2026-09-22 after reading those items.

Options for the table: show it as text through `st.table` (cannot draw a spanning header, so the
layout that carries the meaning is lost); show only the rows the two texts sit in (loses the group
header and the control column, which is what orients the reader); show the whole table as HTML with
the paper's spans, caption and footnotes (chosen). Options for the marks in it: mark the claimed
cell (answers the forced choice for the reviewer); mark nothing (the reviewer hunts through the
grid); mark the cells of both texts alike, each with its label (chosen).

## Decision

Each text is rendered exactly as the paper wrote it, escaped and nothing else; no emphasis is put
on the value or anywhere in a text. When either text is a table cell, the whole table it sits in
is drawn once beneath the two texts, with its label, caption and footnotes and the paper's row and
column spans, and the cells of A and B carry their labels as identical marks. The tables are
carried on the `ReviewItem` in document order, so the page needs no access to the paper and the
record holds what was shown; the JATS reader keeps each table as a unit beside its cell passages.

## Trade-off accepted

The reviewer has to find the value in the text themselves, which costs a moment per item; that is
the price of a screen that does not answer its own question. The page renders its own HTML for the
table, which is one more thing to keep readable on a phone and one place where a paper's characters
must be escaped by hand. Items extracted before this decision carry no table and have to be
re-extracted to get one.
