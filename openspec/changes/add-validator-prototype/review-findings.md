# Code review of `feat/validator-prototype`, 2026-09-21 (`/code-review high` at `9e8f555`)

Ten findings, ranked. None was observed in the two live runs; each is a hole a later run
would fall through. Status as of 2026-09-22 (Yoav's decision): **1, 2, 3, 4, 8 and 9 fixed**
(commits `8050e57`, `62da405`, `9d03f7e`); **7 is moot**, the highlighting it concerned is gone
(ADR-0940, `da690d0`); **5, 6 and 10 stay open** for the rebuild.

| # | Where | Finding | Fix |
|---|---|---|---|
| 1 | `extraction.py` `verify_drafts` | The "quote states the value" check runs on the raw quote, headers included, while `verify` and the stored `Quote` use only the cell part. A value present only in a header (e.g. `500` from `column: CIP (ng/mL) / 500`) passes and is stored with a cell reading something else. | Run `quotes.states_value` on `quotes.cell_text(quote)`. One line plus a test with a header carrying the number. |
| 2 | `distractor.py` `choose_second_text` | A second-text call that raises `ModelRefused` (usage attached) is never recorded in the ledger; the ceiling and the paper's spend miss every such call. | Same `try/except` as `extraction._one_call`: record `cost(model_id, failure.usage)` then re-raise. |
| 3 | `jats.py` `_pieces` | `<sup>`/`<sub>` flatten with no marker: `2.5 × 10<sup>8</sup>` becomes `2.5 × 108`, so a correct value fails the checker and a wrong one can pass. | Render superscripts as `^8` (or Unicode superscripts) in passage text; fold them in `quotes.fold`; test on a value, not a header. |
| 4 | `store.py` `load_run`, `extraction.py` claim ids | Item ids `<pmcid>-<n>-item` and paper rows keyed by `pmcid` carry no run, so a second question touching the same paper is silently skipped on load. | Key items `<run>-<pmcid>-<n>` and papers `(run_id, pmcid)`; migration is additive (new tables are empty in every deployment). |
| 5 | `extraction.py` retry | The paid retry fires for quote failures on rejected candidates, a pool nothing reads. | Retry only for claim failures; or wire `rejected` into the second-text selector as `records.py` says. |
| 6 | `cli.py` `extract_run` | Unlicensed papers are fully extracted, then everything is discarded. | Check the licence before `extract`; end the paper in its state with no call. |
| 7 | `review.py` `highlight` | Bolds every number in the value, uncertainty included, so unrelated `1`s light up. | Use `quotes.numbers_in` over the asserted part of the value. |
| 8 | `openrouter.py` | `reported_cost_usd` is always `None`: the request never sends `usage: {include: true}`. | Add it to the body; assert on it in the request test. |
| 9 | `cli.py` | An unpriced `--model` fails every paper one by one and overwrites the run's results. | Refuse an id not in `spend.PRICES` beside the credential check, before any paper. |
| 10 | `records.py` docstring, `src/bionumbers/CLAUDE.md` | Both place `ExtractionOutput` in `records.py`; it lives in `extraction.py`. | Correct the two sentences. |

## Asked for at the same time (Yoav, 2026-09-22): show the whole table — **built** (ADR-0940)

Built on 2026-09-22 as proposed below, with two differences: both texts' cells are marked
alike with their labels rather than the claimed cell highlighted (a highlight would answer the
forced choice), and footnotes come with the caption. The value is no longer emphasised in the
texts either, at Yoav's request. The original proposal follows for the record.

When a claim's text is a table cell, the reviewer needs the table it sits in, with its caption
— Table 3 of PMC13118904 has a spanning group header (`CIP (ng/mL)`, `NLC-CIP (ng/mL)`) over
concentration sub-headers and a control column `C`, and two header fragments do not orient
anyone. Proposed shape, not yet built:

- `jats.py` keeps each table as a unit: label, caption, header rows with spans, body rows, the
  id of every cell.
- `records.ReviewItem` carries the table (or tables) its texts come from, so the page needs no
  access to the paper; `item_json` carries it through the store unchanged.
- The page keeps texts A and B as the cells with their headers (the choice is between those
  two) and shows the full table once beneath them, caption included, with the claimed cell
  highlighted and the second text's cell marked when it is in the same table.
- Spec change in `review-task`, requirement "One claim, one item, one screen": replace "not as
  the whole table" with the sentence above.
- Existing items do not carry a table; the twelve current items need a re-extract (~$1.30).

About a day of work across reader, record, page and tests. Waiting for Yoav's go.
