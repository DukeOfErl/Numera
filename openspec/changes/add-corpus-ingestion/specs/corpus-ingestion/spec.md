## Purpose

Turns the public BioNumbers export into a JSONL corpus the ask agent can read, so a corpus is
something a reader produces from the published source rather than something they are handed. The
corpus itself is never committed; this capability is what makes that possible.

## ADDED Requirements

### Requirement: Ingest the published export into a JSONL corpus

The system SHALL provide a command that takes the path to the BioNumbers export — a single HTML
`<table>` published with an `.xls` extension, around 27 MB and 14,297 rows over 14 columns — and
writes a JSONL corpus, one JSON object per line, one line per data row.

The command SHALL accept the file as published, without the reader converting, renaming or
pre-processing it.

#### Scenario: A published export becomes a corpus

- **WHEN** the command is run against an export file
- **THEN** it writes a JSONL file whose line count equals the number of data rows in the export
- **AND** each line is a single JSON object

#### Scenario: The source is not where the reader said

- **WHEN** the named source file does not exist or cannot be read
- **THEN** the command fails with a message naming the path
- **AND** exits non-zero
- **AND** writes no corpus file

### Requirement: The output satisfies the ask agent's corpus contract

Every emitted line SHALL carry the keys the ask agent's corpus loader requires: `bnid`, `property`,
`organism`, `units`, `value`, `range_low`, `range_high`, `reference`, `reference_pubmed_id`,
`measurement_method`, `comments`, `keywords`.

`bnid` SHALL be a number. `value`, `range_low` and `range_high` SHALL each be a number or JSON
`null` — never a string, and never `""`, which the loader reads as a present value and would use to
blank out every range-only entry. `keywords` SHALL be a JSON array of strings. The remaining keys
SHALL be a string or `null`.

Emitting keys beyond that set is permitted: the loader ignores what it does not model. The fields
carried alongside — the per-record source stamp and the `range_fused` predicate required by
`ingestion-integrity`, and the parse flags required by `measurement-cleaning` — rely on that, and
SHALL NOT require any change in the consumer for a corpus to load. A consumer that chooses to read
`range_fused` adds one optional field with a default; the twelve required keys are unchanged.

#### Scenario: A corpus loads

- **WHEN** a corpus produced by the command is passed to the ask agent's corpus loader
- **THEN** it loads without error
- **AND** yields one entry per line

#### Scenario: An entry with no single value

- **WHEN** a row carries a range but no scalar value
- **THEN** its line has `value` as `null`, not `""` or `"None"`
- **AND** the loaded entry reports the range as its value

#### Scenario: Provenance fields the loader does not model

- **WHEN** a line carries fields outside the required set
- **THEN** the loader accepts the line and ignores them

### Requirement: Every line stands on its own

The ask agent's loader rejects an entire corpus on its first unusable line, so a single malformed
line costs the reader all ~14,297 entries. The system SHALL therefore emit only lines it has
already turned into complete, well-typed records, and SHALL never emit a partially-built record for
a row it could not fully interpret.

A row that cannot become a record SHALL be counted and reported rather than emitted (see
`ingestion-integrity`).

#### Scenario: An uninterpretable row does not poison the corpus

- **WHEN** the export contains a row that cannot be turned into a record
- **THEN** no line is emitted for that row
- **AND** the remaining lines still load as a corpus

### Requirement: A run that does not finish leaves no corpus behind

A truncated corpus is indistinguishable from a complete one once written: it loads, it answers
questions, and it is silently missing entries. The system SHALL make the output file appear only on
successful completion, so an interrupted or failed run leaves either the previous corpus or no file
at all — never a partial one.

#### Scenario: The run fails partway

- **WHEN** ingestion fails after some rows have been processed
- **THEN** no new corpus file is left at the output path

### Requirement: The whole export is processed by default

The system SHALL process every data row unless explicitly asked for fewer. A row limit SHALL be
available for sampling, and a run that used one SHALL say so in its report, so a sample is never
mistaken for the corpus.

#### Scenario: Default run

- **WHEN** the command is run with no limit
- **THEN** every data row in the export is processed

#### Scenario: Sampled run

- **WHEN** the command is run with a row limit
- **THEN** at most that many rows are processed
- **AND** the report states that the run was limited and to how many rows

### Requirement: The corpus cannot be committed by accident

The corpus is licensed material this project does not redistribute. The default output location
SHALL be a path git ignores, and the repository SHALL document where to obtain the export and how
to cite BioNumbers.

#### Scenario: Default output is ignored

- **WHEN** the command is run with default settings and the repository's status is inspected
- **THEN** the corpus file does not appear as an untracked addition
