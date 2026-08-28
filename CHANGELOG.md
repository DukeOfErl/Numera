# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow it going forward. Dates are ISO 8601 (YYYY-MM-DD).
Versions are git tags (`vX.Y.Z`) using [semver](https://semver.org/)'s
pre-release convention: `0.y.z` while the app's shape may still change with
any release; `1.0.0` when it stabilizes.

## [Unreleased]

### Added

- **`bionumbers-ingest`** — a command that turns the published BioNumbers export
  (an HTML table served as `.xls`) into a JSONL corpus. The export is fetched by
  the reader and nothing derived from it is ever committed, so a corpus stops
  being an artefact only its author possesses ([ADR-0200]).
- **A manifest beside every corpus**, recording the source's checksum, size and
  modification time, when the run happened, which version ran, and every count
  from the report. Each record also carries twelve characters of that checksum.
  The export has no date or version anywhere in it, so without this two corpus
  files cannot be told apart or dated ([ADR-0240]).
- **A run report** of what could not be interpreted, with a count per flag —
  zeroes stated rather than omitted.
- **`range_fused`** on every record: the stored bounds may come from two
  different quantities, because bounds are the lowest and highest number in the
  cell. 1,418 records of the current export ([ADR-0230]).
- **`range_percent_deviation`** in `parse_flags` where the bounds came from a
  relative uncertainty: `±23%` is a fraction of the value, not a quantity, and
  reading it as one gave a 46-unit interval around a value of 0.488.
- **`range_qualified`** on every record: the source did not state a closed
  interval. `<0.001` stored as the interval 0.001–0.001 asserts an exact equality
  where the source said *less than*. 2,233 records.
- The command **refuses to run where git would track its output**, naming the
  repository, rather than writing unlicensed data onto a committable path.

### Changed

- The whole export is processed by default; a row limit must be asked for and is
  recorded in the manifest. A sampled corpus looks complete and is not.
- The corpus appears at its destination only after the last record is written, so
  a failed run leaves the previous corpus or nothing — never a short one.
- JSONL is the only output format; the parquet output and `pyarrow` are dropped,
  since a second serialization path is a second place the contract can drift
  silently ([ADR-0220]).

### Fixed

Defects in the ported first-pass ingester, each of which produced a plausible
number rather than an error:

- Markup was stripped before entities were unescaped, and the export's injected
  markup arrives escaped — so the strip matched nothing, the unescape
  manufactured a live tag, and 10,206 of 14,294 records carried `<IMG …>` in
  their keywords while the flag meant to report it read **zero**, because its
  condition was unreachable.
- Any angle bracket was treated as markup, deleting scientific content: variable
  notation (`<D>`, `<Csat>`) and whole clauses after a less-than sign, including
  a p-value and a DOI fragment, out of `Comments`.
- `2×10^5` was read as three numbers and `150,000` as two, inflating the
  fused-range counts by nearly a third.
- The plus-or-minus deviation was the first number in the cell rather than the
  one after the sign, and 138 cells with more than one `±` collapsed into a
  single fabricated interval, unflagged.
- A hyphen after a unit was read as a sign, so `5%-10%` gave −10 to 5 on 203
  records; a number without a leading zero lost its decimal point on 20.
- Bounds written after a "Table link" URL were discarded on 10 records.
- Three cells wrote an exponent once for both bounds — `1-2×10^9 cells/ml` stored
  as 1 to 2,000,000,000 — now flagged rather than corrected.

[ADR-0200]: docs/decisions/0200-ship-an-ingester-not-a-prepared-corpus.md
[ADR-0210]: docs/decisions/0210-verifying-a-contract-owned-by-another-branch.md
[ADR-0220]: docs/decisions/0220-jsonl-only.md
[ADR-0230]: docs/decisions/0230-flag-and-count-never-correct.md
[ADR-0240]: docs/decisions/0240-stamp-every-ingest.md
