## Why

The harvest demo shows numbers taken from papers and reviewed up a ladder of trust, but the only way
to see them is the review page. A reader asks questions of the ask agent, and the ask agent reads
only the ingested BioNumbers corpus — it cannot see a single harvested number, and nothing it says
tells a reader how far to trust the entry behind it. For the demo (~2026-10-17) the agent has to
answer from the harvest store and say, beside every citation, how well reviewed that entry is.

## What Changes

- The ask agent can be pointed at the harvest store instead of a JSONL corpus. The store is read
  only, never written. The JSONL corpus keeps working exactly as it does today.
- From the store the agent sees two kinds of entry: the curated BioNumbers entries (cited by their
  BNID, as now) and every harvested entry from every domain the store holds — biology, organismal,
  biophysics, physics, chemistry — one entry per extracted value, cited as `[[PMC2652108-1]]`
  (the paper's PMCID and the value's number within it).
- A harvested entry carries what a reader needs to judge it: the property as the paper words it, the
  organism, the value as the paper wrote it and the numbers read from it, the supporting quote,
  each condition the paper states (method among them) and each it does not, the paper itself, and
  whether the value was **calculated** rather than measured — with the passages it was calculated
  from.
- Where the numbers read from a value disagree with the kind of value the extraction recorded, the
  entry carries a caution and its text is what is stated, rather than a number that may be misread.
- Every cited entry shows its **trust tier as stars**, drawn by the application from the store —
  never written by the model. The rule is ADR-0990's (`bionumbers.tiers`): the highest role that
  approved, a separate caution where anyone objected, zero stars where no one approved, and a mark
  wherever the tier was set by a simulated review.
- The agent is told each entry's tier so it can prefer better-reviewed entries, but never shown a
  reviewer's own words.
- The text the review shows beside a value to test the reviewer (the "second" text, a distractor in
  402 of 452 items) never reaches the agent.

Out of scope: authors and an author tier (deferred entirely); review by the ask agent's readers;
evaluation runs over the store; a live view of decisions made after the store was loaded.

## Capabilities

### New Capabilities

- `store-corpus`: reading the harvest store as the agent's corpus — what is loaded, how a harvested
  entry is identified and what it carries, how its value is read, and what never reaches the agent.

### Modified Capabilities

- `grounded-answering`: adds that a cited entry from the store is shown with its trust tier, drawn
  by the application, with a caution where the entry is disputed and a mark where the tier is
  simulated.

## Impact

- **Code:** `scinumbers_ask` gains a store loader beside `corpus.load`; `Entry` gains the fields a
  harvested entry carries and an identifier that need not be an integer; `citations` reads the new
  identifier form; `tools` shows the new fields and the tier; `entries_table` and both drivers draw
  the stars. `repository` indexes the quote, conditions, domain and topic.
- **Dependencies:** the ask package imports `bionumbers` (`tiers`, `readings`) — a new direction,
  chosen so the tier rule and the value parser each have one definition. Those two modules need only
  SQLAlchemy and pydantic, so the `ask` extra names pydantic explicitly and needs nothing from
  `validator`.
- **Configuration:** a store path or URL beside `SCINUMBERS_CORPUS`; the data itself stays in
  `BioNumbers-review/harvest-demo.sqlite`, outside every repository.
- **Branch:** stacked on `feat/simulated-review` (for `bionumbers.tiers`); rebases onto `dev` once
  that work merges.
- **ADRs:** block `1600`–`1690`.
