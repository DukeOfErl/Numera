# corpus-ingestion Specification

## Purpose
Turns the public BioNumbers export into a JSONL corpus the ask agent can read, so a corpus is
something a reader produces from the published source rather than something they are handed. The
corpus itself is never committed; this capability is what makes that possible.
## Requirements
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

Every emitted line SHALL carry the keys the ask agent's corpus loader requires: `entry_id`, `property`,
`organism`, `units`, `value`, `range_low`, `range_high`, `reference`, `reference_pubmed_id`,
`measurement_method`, `comments`, `keywords`.

`entry_id` SHALL be a number. `value`, `range_low` and `range_high` SHALL each be a number or JSON
`null` — never a string, and never `""`, which the loader reads as a present value and would use to
blank out every range-only entry. `keywords` SHALL be a JSON array of strings. The remaining keys
SHALL be a string or `null`.

The identifier key SHALL NOT name the source's own vocabulary for it. The consumer is not named for
one database, and a corpus produced from a second source SHALL satisfy this same contract without
carrying the first source's terminology in its keys. The ingester's internal names and its run report
MAY keep the source's vocabulary: those describe what was read, and are not a contract with a reader.

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

#### Scenario: The identifier key

- **WHEN** a record is emitted
- **THEN** its identifier is carried under `entry_id` as a number
- **AND** under no key naming the source it came from

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

### Requirement: An export beside a missing corpus can produce one

A reader who has downloaded the export has done the only step that cannot be automated. Requiring
them to also invoke the ingester before the agent will start is a third step whose only cause is that
nothing told the agent the file was there, and the error it gets instead — that no corpus exists at
the configured path — is accurate while the material to build one sits in the same directory.

The system SHALL provide a resolver that, given a configured corpus path, reports: the path the
corpus occupies or would occupy, the export that could produce it if one is present, and whether a
build is required. Reporting SHALL be separate from building, so that a caller can tell a reader what
is about to happen before a 27 MB read begins.

#### Scenario: A corpus is already there

- **WHEN** the configured path holds a corpus
- **THEN** the resolver reports no build is needed, and names that path

#### Scenario: An export sits beside the missing corpus

- **WHEN** the configured path holds nothing and `BioNumbers.xls` is in the same directory
- **THEN** the resolver reports that a build is needed, naming both the export and the corpus path

#### Scenario: The configured path is the export itself

- **WHEN** the configured path is an `.xls` export
- **THEN** the resolver reports the corpus path beside it, and builds there rather than in the cwd

#### Scenario: Neither is present

- **WHEN** the configured path holds nothing and no export is beside it
- **THEN** the resolver reports no build is possible, and the caller's own error stands

### Requirement: A corpus that exists is never rebuilt

The resolver SHALL NOT rebuild a corpus that is present, whatever its modification time and whatever
digest its manifest records.

A corpus someone produced deliberately — from a different export, with a row limit, or edited — being
replaced without being asked is a worse outcome than a stale one being read. Staleness is invisible
from the answer side and "the file changed under me" is the hardest class of defect to trace, so the
rule is absolute rather than heuristic. Detecting staleness, if it is ever wanted, is a report and
never an action.

#### Scenario: The corpus is older than the export

- **WHEN** a corpus exists and the export beside it is newer
- **THEN** the existing corpus is used and nothing is written

### Requirement: A build through the resolver is refused on the same terms as the command

The resolver SHALL build through the ingest operation, so that a build refused because git would
track its output is refused here too, before anything is read.

A convenience path that bypasses the refusal would be worse than no convenience path: it is the one
irreversible mistake this project can make, and it would be made by a caller who never asked to write
a file at all.

#### Scenario: The corpus path is one git would track

- **WHEN** a build is needed and the corpus path lies in a repository that does not ignore it
- **THEN** the build is refused, naming the repository, and nothing is written

### Requirement: A build is announced before it begins, not after it ends

Where a driver builds a corpus rather than failing, it SHALL say so before the
build starts, and SHALL name both the export being read and the path being
written.

A build takes about a minute. Announced afterwards, or not at all, the first
launch is indistinguishable from a hang -- and a page shows an empty frame for the
whole of it. Both paths are named because the build can be refused on its
destination, and a reader told only what was read cannot tell which path was
rejected.

#### Scenario: A corpus is built on first launch
- **WHEN** a driver finds an export and no corpus
- **THEN** the notice appears before any building work is done
- **AND** it names the export it will read and the path it will write

#### Scenario: A corpus is already present
- **WHEN** a driver finds a corpus at the configured path
- **THEN** nothing is announced, because nothing is built

### Requirement: A corpus that cannot be built is explained, not raised

A driver SHALL report a refused or impossible build the way it reports a missing
corpus: as a message a person can act on, never as a traceback.

Three conditions reach a reader here -- the destination is somewhere git would
track the corpus, the ingestion component is not installed, or there is no export
to build from -- and all three are configuration a person can fix. The second SHALL
name the export that was found and how to use it without that component, since an
answer of "not installed" is less useful than one that says what to do with the
file already present.

#### Scenario: The destination would be committed
- **WHEN** the build is refused because git would track the corpus
- **THEN** the driver states the path and the repository, and does not raise

#### Scenario: The ingestion component is absent
- **WHEN** an export is present and the component is not installed
- **THEN** the message names the export and the command that would convert it

#### Scenario: There is nothing to build from
- **WHEN** neither a corpus nor an export is present
- **THEN** the ordinary missing-corpus message stands, unembellished

