## Why

The question-first validator found the right paper 4 times in 32: a full-text search for a
property and an organism returns papers that mention both and measure neither. The extractor was
right every time. So the prototype turns round — papers are harvested ahead of any question for
the numbers a scientist outside the study would reuse, questions are answered from the resulting
store, and trust is earned afterwards through review (ADR-0950). A presentation on 2026-10-17
needs the whole shape visible: harvested entries from more than one domain, a curated tier to
compare them with, and a review pipeline that rates them.

## What Changes

- A run can start from a hand-chosen list of articles instead of a search; each article is asked
  once, with no question, for its reusable values, at most twenty.
- The values wanted are those of one named domain — biology, biophysics, chemistry or physics —
  and the domain is recorded on every entry.
- Each entry carries three labels the model writes — a property name, a class, and the organism
  or material — and a value reported beside others of its kind is named by its condition.
- A value an article computes from other publications' data is an entry, under its own category.
- A hand-chosen article's licence is taken from the index when its document states it in prose.
- Every entry records the model that answered, beside the one asked for.
- A cited second text is never another source's value for the same property in the same organism.
- BioNumbers' own entries in the demo's slice that nothing marks doubtful are loaded as a curated
  tier, the top of the trust order.

Built on `feat/harvest-prototype`, which branches from the unmerged `add-validator-prototype`;
this change's specs read as additions to that pipeline. The simulated review runner is a separate
change on `feat/simulated-review`.

## Capabilities

### New Capabilities
- `number-harvest`: starting a run from chosen articles, the domains a harvest can ask in, the
  labels and bounds of a harvested entry, and what is recorded about how it was produced.
- `curated-tier`: which BioNumbers entries may stand at the top of the trust order, and how the
  tier is loaded.

### Modified Capabilities
<!-- None in openspec/specs/: the validator's capabilities are still deltas on the unarchived
     add-validator-prototype, and the second-text restriction is recorded there. -->

## Impact

- `src/bionumbers/`: `harvest.py` (scopes), `curated.py` (new), `extraction.py`, `records.py`
  (`Claim` labels, `Fingerprint.scope`, `Fingerprint.answered_by`), `europepmc.py`
  (`index_record`), `store.py` and `sql/review.sql` (`curated_entry`), `cli.py` (`harvest`,
  `curate`).
- The BioNumbers corpus is read at run time and never committed; `curated_entry` holds a copy of
  423 of its entries, which matters if the review database is ever shared.
- ADRs 0950 (in the validator's block), 1500 and 1510.
