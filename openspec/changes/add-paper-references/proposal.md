## Why

The ask agent's entries table is to show each entry's source as a formatted reference -- author,
year, title, journal, volume, pages, DOI -- written by the application rather than by the model.
The store holds only what discovery kept: the identifiers, the title and the year. No row has the
authors or the journal, and the full text that states them is read on every harvest and then
dropped. Asked for by the `add-ask-over-store` session on 2026-10-16, approved by Yoav.

## What Changes

- A paper's bibliographic record, as one CSL-JSON item, is read from its JATS front matter
  alongside the identifiers it already yields, and travels with the paper into the run's files
  and the store (`review_paper.csl_json`).
- A store loaded before the column existed is filled from the cached full text by
  `bionumbers upgrade-store --data`.
- The style is applied at display, by whoever reads the record (ADR-1750).

## Capabilities

### New Capabilities

### Modified Capabilities
- `source-discovery`: the record carries the bibliographic reference, not only the identifiers.

## Impact

- `src/bionumbers/jats.py` (the record from the front matter), `records.py`, `store.py`,
  `cli.py`, `sql/review.sql`; `harvest-demo.sqlite` filled and backed up.
- Out of scope: the 423 curated entries' BioNumbers reference strings, which name no PMCID here.
