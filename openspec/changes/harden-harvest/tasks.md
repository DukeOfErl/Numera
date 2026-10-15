ADR block: `1700`–`1740` (reserved in `CLAUDE.md`).

## 1. The twenty-entry bound (was add-harvest-prototype 6.5, review finding 3)

- [ ] 1.1 Verified entries beyond the twentieth are dropped before the second-text call, inside the extraction operation; the article's record counts the drop
- [ ] 1.2 Tests: thirty in, twenty kept in order, no second-text call for the ten, the count recorded; twenty or fewer, nothing dropped

## 2. Repeat readings (was 6.6, review finding 1)

- [ ] 2.1 Decide D2 (derived at read time, or a recorded link) against a store holding one paper read twice; write the ADR
- [ ] 2.2 `next_item` serves one article's items together across runs
- [ ] 2.3 An entry shows its article's other readings, and which report the same property with a different value; nothing merged or dropped
- [ ] 2.4 Tests for the three scenarios in `review-task`

## 3. Small fixes (was 6.8, 6.9; review finding 8)

- [ ] 3.1 The review page keeps one engine across reruns when its database comes from `BIONUMBERS_REVIEW_DB_URL`
- [ ] 3.2 A line whose first non-blank character is `#` is a comment in a PMCID file; test with an indented comment
- [ ] 3.3 The committable-run-folder guard lives in the operation that creates the run folder, called once

## 4. Before hand-over

- [ ] 4.1 Map the three requirements in `tests/test_spec_conformance.py` (recorded as gaps until then)
