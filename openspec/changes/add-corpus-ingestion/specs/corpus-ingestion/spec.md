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

### Requirement: The same source produces the same corpus

Because every reader fetches the export and builds the corpus themselves, two readers comparing their
corpora is the only way either can tell whether they hold the same data. That comparison is worthless
unless the same source produces the same bytes.

The system SHALL produce a byte-identical corpus from a given source file, independent of when it runs
or of any run-to-run variation in the interpreter. Two manifests of one source SHALL differ only in
the ingest date, which is a fact about the run rather than about the data.

#### Scenario: Two builds of one export

- **WHEN** two runs ingest the same source file
- **THEN** the two corpus files are byte-identical
- **AND** their manifests differ only in the ingest date

### Requirement: The command refuses to write where git would track the corpus

The default output path is relative, so a run started from the wrong directory writes the corpus into
whichever repository the caller is standing in. Three checkouts of this project share one origin and
one of them tracks the default branch, so that is a direct route from a mistyped `cd` to 19.5 MB of
unlicensed data in a public history — the one mistake this capability can make that cannot be undone.

A `.gitignore` entry guards only the repositories someone remembered to edit. The system SHALL
therefore ask git whether it would track the output file, and SHALL refuse to run when it would,
naming the repository and exiting non-zero without writing anything. Where git reports the path as
ignored, or there is no repository, or git cannot be consulted, the run SHALL proceed.

#### Scenario: The output would be tracked

- **WHEN** the output path lies in a repository that does not ignore it
- **THEN** the command refuses, names that repository, and writes nothing

#### Scenario: The output is ignored, or outside a repository

- **WHEN** the output path is git-ignored, or lies outside any repository
- **THEN** the command runs normally

#### Scenario: Any caller is refused, not only the command

- **WHEN** the ingest operation is invoked directly rather than through the command
- **THEN** it refuses on the same condition, before reading the source

The refusal belongs to the operation. Placed in the command it protected exactly one caller, and the
operation invoked as a library wrote the corpus onto a committable path in silence — a bypass that
stayed invisible while the command was the only caller, and that a second caller would have taken.

### Requirement: Each key carries the value of its own column

Requiring that the twelve keys are *present with an accepted type* is not enough, because `null` is an
accepted type for ten of them. A record with every text field empty satisfies that requirement
completely, loads without error, and answers questions with no organism, no reference and no
measurement method — while every test of the key set passes.

The system SHALL therefore carry each column's value into its own field, and that mapping SHALL be
asserted per column rather than inferred from the keys being present.

#### Scenario: Every column reaches its field

- **WHEN** a row whose fourteen columns each hold a distinguishable value is cleaned
- **THEN** each of the record's fields carries the value of the column it names

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
