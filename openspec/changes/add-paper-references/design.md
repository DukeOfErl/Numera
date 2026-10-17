## Context

Chicago author-date, as the ask agent will show it, needs authors, journal, volume, issue and
pages. Europe PMC's lite index record has none of these; the JATS front matter has them all, in
two layouts over the 130 cached papers (the author type on each `<contrib>`, or on the
`<contrib-group>`), with editors and reviewers typed the same two ways.

## Goals / Non-Goals

**Goals:** every paper the harvest reads carries a record the application can format; the 48
papers of the demo store get theirs without a re-run.

**Non-Goals:** formatting the citation (the reader's job: ADR-1750); a reference for curated
entries; fetching anything the cache does not hold.

## Decisions

### D1. CSL-JSON stored, the style applied at display

One `TEXT` column, `review_paper.csl_json`, holding one CSL-JSON item. The alternative, a
formatted string, would fix the style in the store and need a refill to change it. CSL-JSON is
the interchange form every citation processor reads, so the agent, the dashboard and an export
can each format it their own way. ADR-1750.

### D2. Read where the front matter is already parsed

`read_jats` returns the record on `Document.csl`; the harvest writes it on the `Paper`, and
`extract` fills it for a paper discovery left bare. No second parse, no second fetch. The fill
for an older store goes through the same reader over the cache (`upgrade-store --data`), so one
function decides what a record holds.

### D3. Who is an author

A `<contrib>` whose `contrib-type` is `author`, or that has none while its group's
`content-type` is `author`. Nobody else -- a contrib typed neither way does not occur in the
cache, and leaving one out costs a shorter citation where counting it could name an editor.

### D4. Which date

The print date, else any date of the article's own, else the volume's `collection` date; the
`year` column follows the same choice, so the two never disagree. In 2 of 130 cached papers the
collection date names the year after the article appeared.
