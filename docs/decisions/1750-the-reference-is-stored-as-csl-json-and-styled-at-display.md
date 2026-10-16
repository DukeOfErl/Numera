# ADR-1750: The bibliographic record is stored as CSL-JSON; the style is applied at display

- **Status:** accepted
- **Date:** 2026-10-16
- **Pull request:** not yet opened — branch `feat/paper-references`

## Context

The ask agent is to show each entry's source as a formatted reference (Chicago author-date, to
begin with), written by the application from the store rather than by the model: a model-written
citation is one more thing a reviewer cannot check by reading. The store held the PMCID, PMID, DOI,
title and year; a reference also needs the authors, the journal, the volume, the issue and the
pages, all of which are in the JATS front matter the harvest already parses and none of which any
row kept.

Three ways to keep them were on the table: a formatted reference string per paper; one column per
field (authors as JSON, journal, volume, issue, pages); or one CSL-JSON item per paper.

## Decision

One `TEXT` column, `review_paper.csl_json`, holding one CSL-JSON item (`type`, `id`, `title`,
`author` as `{family, given}` or `{literal}` in the paper's order, `container-title`, `volume`,
`issue`, `page`, `issued` as `date-parts`, `DOI`, `PMID`, `PMCID`; a key the front matter does not
fill is absent). The reader formats it: the agent, a dashboard and an export each in their own
style, from the same record. `Paper.csl_json` carries the serialised item from the harvest into the
run's files and the store; `read_jats` is the one place that decides what the item holds, and
`upgrade-store --data` runs the same reader over the cache for a store loaded before the column
existed.

## Trade-off accepted

A formatted string would need no library to show and no decision about style at display time; it
would also fix the style in the store, and a change of style would be a refill of every row from
text that may no longer be cached. Columns per field would be queryable in SQL, which nothing asks
for yet, at the cost of a schema change for every field a style turns out to need. CSL-JSON is the
form every citation processor reads and the one a later processor would want anyway; its cost is
that the store holds a blob SQL cannot see into, and that each reader formats it -- the ask agent
with its own Chicago function for now, a processor later if styles multiply.
