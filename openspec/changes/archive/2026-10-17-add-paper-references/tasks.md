ADR block: `1750`–`1790` (reserved in `CLAUDE.md`).

## 1. The record

- [x] 1.1 `read_jats` returns the CSL-JSON item on `Document.csl`; `_issued` picks the date and `year` follows it
- [x] 1.2 `Paper.csl_json`, `review_paper.csl_json` in `store.py` and `sql/review.sql`, written on load
- [x] 1.3 The harvest writes it; `extract` fills a paper discovery left bare
- [x] 1.4 `store.fill_references`; `upgrade-store --data` fills an older store from the cache
- [x] 1.5 Tests: the two author layouts, editors and reviewers left out, a collaboration, four page shapes, collection vs own date, absent not empty; load, fill, the CLI
- [x] 1.6 ADR-1750, spec delta, conformance mapping

## 2. The demo store

- [x] 2.1 `upgrade-store --data` over `harvest-demo.sqlite`; every paper with full text holds a record
- [x] 2.2 `~/scinumbers-data/backup.sh`
- [x] 2.3 Tell the `add-ask-over-store` session the column and the shape
