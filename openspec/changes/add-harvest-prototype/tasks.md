## 1. Harvest mode (ADR-0950)

- [x] 1.1 `bionumbers harvest` starts a run from PMCIDs; extraction asks each paper once with the harvest instruction and a scope in the user turn
- [x] 1.2 Three model-written labels on every claim; the item's question is built from them
- [x] 1.3 A value computed from other publications' data is a claim, under `DERIVED_FROM_PUBLISHED`
- [x] 1.4 At most twenty claims a paper, with harvest's own output bound
- [x] 1.5 A cited second text is never the same property in the same organism

## 2. Domains (ADR-1500)

- [x] 2.1 Scopes for biology, biophysics, chemistry and physics; `--scope` on `harvest`
- [x] 2.2 The scope's name on every fingerprint; a run without one reads as biology
- [x] 2.3 A value belonging to no organism is labelled with its material or system
- [x] 2.4 A value beside others of its kind is named by its condition; the control by nothing

## 3. Records

- [x] 3.1 A hand-chosen paper's licence comes from the index's core record
- [x] 3.2 `Fingerprint.answered_by` from the provider's response

## 4. Curated tier (ADR-1510)

- [x] 4.1 `curated.refusal`: the slice and ten signs of doubt, each with a negative case
- [x] 4.2 `curated_entry` in `store.py` and `sql/review.sql`; `load_curated` replaces the tier
- [x] 4.3 `bionumbers curate` reports what it loaded and what it left out, by reason

## 5. Seeding the demo

- [x] 5.1 Twenty-five biology papers harvested with GPT-6.1 Sol into `harvest-demo.sqlite`
- [x] 5.2 Five papers in each new domain (planarians, cytoskeletal mechanics, cytoskeleton chemistry, the glass transition): 152 claims from 15 papers, $3.77; three set aside for no methods section, two left unread by the run budget
- [x] 5.3 The curated tier loaded into `harvest-demo.sqlite` (423 entries)

## 6. Before hand-over

- [x] 6.1 Conformance mapping for every requirement in this change
- [x] 6.2 Full suite green (2069 passed, 2026-10-07)
