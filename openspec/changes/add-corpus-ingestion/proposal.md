## Why

The ask agent reads a JSONL corpus that this project must never commit — its licensing is
unresolved (ADR-0170, recorded on `feat/ask-agent`). Today the only way to
give a reviewer a runnable corpus is to hand them a prepared JSONL out of band, which is both
awkward and a quiet act of redistribution. With an ingester in the repository, a reviewer fetches
the public BioNumbers export themselves and turns it into a corpus locally: nothing is
redistributed, and the corpus stops being a thing only its author possesses.

The ingestion code already exists, written against the real 27 MB file and its quirks, in a
private first-pass repository (`~/Bionumbers-first`). This change ports it here, drops the parquet
output the agent has no reader for, and pins the output to the contract
`bionumbers_ask.corpus.load` actually enforces.

**The cleaning semantics in this change are provisional, deliberately.** The goal now is an ingester
that works with `add-ask-agent` as that change was already built; how the corpus *should* be cleaned
is expected to be reconsidered once the ask agent lands and both changes know more about the export
than they do today. Two things are therefore designed to survive that reconsideration, and the rest
is not: the **twelve-key output contract**, which the consumer's loader enforces and this change only
satisfies; and the **`range_fused` seam** — one boolean meaning "these bounds may fuse more than one
quantity", with the flag names behind it internal to cleaning. Everything about *how* a cell
becomes a number — the range notations, the plus-or-minus branch, the unit direction, the fused-range
heuristics — is expected to change, and is written so that it can without a cross-branch negotiation.
The invariants that are not provisional are the ones about output integrity rather than
interpretation: the typing rules (`null`, never `""`), no partial corpus on a failed run, and the
provenance manifest and per-record stamp. A wrongly-cleaned number can be found and fixed later; a
corpus silently missing entries cannot be.

## What Changes

- A new `bionumbers-ingest <file>` command turns the public BioNumbers export — a 27 MB single
  HTML `<table>` carrying an `.xls` extension, ~14,297 rows, 14 columns — into a JSONL corpus.
- The output satisfies `bionumbers_ask.corpus.Entry`: every key that loader requires is present on
  every line, with types it accepts (absent scalars as JSON `null`, never `""`; `keywords` as a
  list). Six provenance fields the loader ignores ride along.
- The source file's known quirks are handled explicitly rather than absorbed: the leading `'`
  text-marker on `Range`; ranges written six different ways (hyphen, `to`, en/em dash, `±`/`+-`/`+/-`,
  unicode minus, scientific notation); the two micrometre glyphs; injected
  `<IMG SRC="/WF_SQL_XSRF.html">` markup; and the ~23% of rows whose `Range` is only a link to an
  external PDF.
- Nothing is silently dropped. Rows that cannot become records are counted and reported, parse
  outcomes are recorded per row as flags, and the run prints a report of what it did.
- Two new parse flags mark a range the cleaner may have fused out of two unrelated quantities:
  bounds are taken as the lowest and highest number in the cell, so a cell naming a second quantity
  contributes a bound to the first. `range_multi_number` marks a cell that yielded more than two
  numbers; `range_prose_between_bounds` marks text standing between the two bounds used. The bounds
  themselves are unchanged — this change makes the class countable, not correct. **What
  `add-ask-agent` consumes is a dedicated boolean, `range_fused`, not any flag name**: `true` when the
  stored bounds may fuse numbers from more than one quantity. The flag names stay internal to cleaning
  and may be renamed, split, merged or dropped as the corpus is better understood; `range_fused` keeps
  answering the same question when they do. It has to be a field rather than a rule over `parse_flags`
  because that list is a reporting vocabulary: eight names today, five of them `range_`-prefixed, and
  only two meaning fusion — `range_plus_minus` and `range_mean_sd_embedded` are *successful* parses.
  On the existing corpus a non-empty test selects 5,148 records and a `range_` prefix 5,494, against
  the 1,445 meant. Marking thousands of correct entries would teach a reader to ignore the marking.
  `parse_flags` and `range_fused` are both present on every record, empty and `false` when clean.
- Every ingest is stamped. The export carries no temporal information whatsoever — none of its 14
  columns is a date, and every date-shaped string in it belongs to a citation — so once a download's
  file time is lost, two corpus files cannot be told apart and neither can be dated. Each run writes
  a manifest beside the corpus (source checksum and size, the source file's modification time as the
  only available proxy for when it was fetched, the ingest date, the row and flag counts, and whether
  a row limit was applied), and stamps each record with a short form of the source checksum so a
  corpus line alone can be traced back to the file it came from.
- Every row is processed by default. The source repository's ingester defaulted to a 200-row
  sample, which produces a corpus that looks complete and is not — the failure mode this project
  is least able to afford.
- The parquet output and the `pyarrow` dependency are dropped: the agent reads JSONL, and a second
  format with no reader is cost without a consumer.
- `pyproject.toml` gains a third work-package extra, `ingest` (`pydantic`), alongside `validator`
  and `ask`, and the `bionumbers-ingest` console script.
- `data/` is added to `.gitignore`, so the tool's default output path cannot be committed by
  accident.

Not in scope: downloading the export (the URL and the citation go in the README, the fetch stays
the reader's); any database or index built from the corpus; changing anything the ask agent reads
the corpus *with*.

Deferred: **correcting** a fused range. The exposure is measured, and the measurement was wrong twice
before it was right, which is worth recording because both errors inflated it.

Counting more than two numbers in the range cell **as stored** gave 1,716 of the entries carrying a
parsed range: an external-link filename's escape sequences supply extra digits (`%20` reads as the
number 20). Counting where the flag actually runs, after the URL is removed, gave **1,222** — and that
figure was still wrong, because the number extractor read `2×10^5` as three numbers and `150,000` as
two. With scientific notation and thousands separators read as one number each, the flag reports
**833** (13.6% of the 6,146 ranged entries, 5.8% of the corpus). So 389 of the 1,222 — nearly a third
— were notation, not fused quantities.

The predicate `range_fused`, which is what a consumer reads, covers **1,445** records (23.5% of ranged
entries, 10.1% of the corpus): the 833 above plus the cells with a second quantity named between the
two bounds.

Of the 833: 346 span less than tenfold and are often several defensible measurements of one quantity,
242 span ten- to hundredfold, 98 span hundred- to thousandfold, 97 exceed a thousandfold, and 50
cannot be judged by ratio at all because a bound is zero or negative. So the flag marks a population
at risk, not a defect count — and the tail is where
the near-certain damage lives.

Two candidate responses exist and neither is chosen here: change the parse so fused ranges are never
emitted, or keep the flag and let each consumer decide. This change does the flagging, which is what
makes either choice measurable.

## Capabilities

### New Capabilities

- `corpus-ingestion`: the command, the pipeline from source file to JSONL, and the output contract
  the ask agent's loader enforces.
- `measurement-cleaning`: turning one raw table row into one canonical record — value and range
  parsing across the notations the source uses, unit normalization, markup stripping, and link-only
  rows.
- `ingestion-integrity`: what a run reports about itself — rows processed, rows skipped, duplicate
  identifiers, per-row parse flags, and the manifest that records which source file a corpus came
  from and when — and the rule that nothing is dropped in silence.

### Modified Capabilities

None. `openspec/specs/` is empty on this branch, and this change adds no requirement to the ask
agent's capabilities: the corpus contract is a constraint this change must satisfy, not a behaviour
it changes.

## Impact

- **New code**: `src/bionumbers_ingest/` — a package of its own, parallel to `bionumbers`
  (grounding validator) and `bionumbers_ask`, per the layout `pyproject.toml` already documents:
  one work package, one source tree, so two branches never edit the same table.
- **New tests**: `tests/` gains the ported cleaning, parsing, validation and end-to-end tests, plus
  the corpus-contract tests this change adds. The HTML fixture is ported with them.
- **`pyproject.toml`**: one new extra (`ingest`), one new console script.
- **`.gitignore`**: `data/`.
- **Docs**: `README.md` (currently empty on this branch), `docs/diagrams/architecture.md` (a
  pipeline diagram), `CLAUDE.md`'s Architecture section, `CHANGELOG.md`, and ADRs `0200`–`0240`.
- **`add-ask-agent`**: no code dependency, but the `range_fused` boolean above is a contract that
  change will consume — the field, not the individual flag names, which stay internal to cleaning.
  Nothing on its side has to change for this one to land: its loader models twelve keys and ignores
  every other, so the flags, the predicate and the record stamp are all invisible to it until it
  chooses to read them, and reading one adds an optional field with a default. That change's task 8.7
  — marking a fused range in its entries table and forwarding the boolean to the model — is blocked on
  this one: no corpus emits `range_fused` yet, and the marking is to be tested against real records
  rather than a hand-written fixture built to match its own assumptions.
- **Dependencies**: `pydantic>=2.6` under the `ingest` extra. No new runtime dependency for the
  other two work packages.
- **Cross-branch**: `bionumbers_ask` does not exist on this branch, so the round-trip against the
  real loader cannot run here. How that is verified anyway is the main open question design.md
  answers.
