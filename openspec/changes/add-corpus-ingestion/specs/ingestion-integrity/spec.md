## Purpose

Makes a run account for itself: how many rows it read, how many became records, what it could not
interpret, and which entries carry a caveat. An ingester that quietly discards rows produces a
corpus whose gaps nobody can see, which is the one failure this pipeline cannot afford.

## ADDED Requirements

### Requirement: Every input row is accounted for

The system SHALL report, for each run, the number of records written and the number of rows skipped
as non-data, and these SHALL account for every row read from the export. No row SHALL be discarded
without appearing in one of those counts.

#### Scenario: Counts add up

- **WHEN** an export of known size is ingested
- **THEN** records written plus rows skipped equals the number of rows read
- **AND** both figures appear in the report

#### Scenario: Nothing to report is still reported

- **WHEN** a run skips no rows and raises no flags
- **THEN** the report states those counts as zero rather than omitting them

### Requirement: A run reports what it could not interpret

The report SHALL state, per run: the number of records, the number of rows skipped as non-data,
duplicate identifiers, how many records carry an external link in place of a scalar, how many carry
no scalar value at all, a count per parse flag of how many records carry it, and how many records
carry `range_fused`.

#### Scenario: The report names its caveats

- **WHEN** a run produces records with parse flags
- **THEN** the report lists each flag with the number of records carrying it
- **AND** states the `range_fused` count separately, so the predicate's population can be compared
  against the flags that raise it rather than inferred from them

#### Scenario: An unparseable cell is flagged, not hidden

- **WHEN** a value or range cell holds text from which no number can be read
- **THEN** the record is still written, with no number in that field
- **AND** the record carries a flag naming what failed to parse
- **AND** the flag appears in the report's counts

### Requirement: Duplicate identifiers are reported, not resolved

Two records sharing an identifier is a property of the published export, not a defect the ingester
should hide. The system SHALL report duplicate identifiers and SHALL keep every record.

#### Scenario: A duplicated identifier

- **WHEN** two data rows carry the same identifier
- **THEN** both records are written
- **AND** the report names the duplicated identifier

### Requirement: Every corpus records which file it came from and when

The export carries no temporal information: none of its columns is a date, and every date-shaped
string in it belongs to a citation. Two corpus files therefore cannot be told apart, and neither can
be dated, once the source download's file time is lost — and that information cannot be recovered
afterwards.

Each run SHALL therefore write a manifest beside the corpus recording: a checksum of the source file
and its size in bytes; the source file's modification time, as the only available proxy for when it
was fetched; the date of the ingest; the ingester's version; the row, skip, duplicate and per-flag
counts the report states; and the row limit, if one was applied.

Each emitted record SHALL additionally carry a short form of the source checksum, so a corpus line
separated from its manifest can still be traced to the file it came from.

The corpus and its manifest SHALL both appear only on a completed run, corpus first; a corpus with no
manifest beside it SHALL be treated as the product of a run that did not finish.

#### Scenario: A manifest beside the corpus

- **WHEN** a run completes
- **THEN** a manifest sits beside the corpus naming the source checksum, the source size, the source
  modification time, the ingest date, and the run's counts

#### Scenario: Two corpora from different sources

- **WHEN** two corpus files produced from different source files are compared
- **THEN** their manifests carry different source checksums
- **AND** each record in each corpus carries the short checksum matching its own manifest

#### Scenario: A sampled run says so in its manifest

- **WHEN** a run applied a row limit
- **THEN** the manifest records the limit that was applied

### Requirement: A sampled run's fingerprint still describes the whole file

A run stopped early by a row limit reads only part of the source, so a fingerprint accumulated during
that read covers only the part read — while being recorded under a name that asserts a fact about the
file. Two different limits that both stop within the first read block then produce the *same*
fingerprint, so two corpora cannot be told apart, which is the failure the manifest exists to prevent.

The system SHALL complete the fingerprint over the rest of the file when a run has not read all of it,
so the recorded checksum and size are always the whole file's.

#### Scenario: A limited run and a full run of the same file

- **WHEN** one run applies a row limit and another does not, over the same source
- **THEN** both record the same source checksum and the same source size
- **AND** both stamp their records with the same short digest

### Requirement: A source that cannot be read whole is an error

Two ways the source can be wrong produce a corpus that is short or shifted while the run reports
success, and both SHALL end the run instead.

A file that ends mid-row is truncated — an interrupted transfer, a half-written download. Reading it
yields every row that parsed and stops, producing exactly the short corpus that loads cleanly and is
missing entries nobody can enumerate. The system SHALL detect an unterminated table and fail.

Cleaning reads columns by name, so a renamed column is invisible to it: rename the identifier column
and every row fails the is-it-data test, so the run writes an **empty** corpus and reports no error at
all; rename any other and that field is absent from every record with nothing flagged. The system
SHALL state the column names it relies on and SHALL fail when the source does not carry them.

#### Scenario: A truncated source

- **WHEN** the source file ends mid-row
- **THEN** the run fails rather than writing the rows it managed to read

#### Scenario: A renamed column

- **WHEN** the source's header row does not carry the expected column names
- **THEN** the run fails, naming which are missing and which are unexpected

### Requirement: A flag that cannot fire is worse than no flag

A flag whose condition is unreachable reports zero and reads as "this does not occur in the source".
The markup flag in the ported implementation is exactly that: its tag pattern is applied before
entities are unescaped, and the export contains no literal tags, so it reports zero on a corpus where
10,206 of 14,294 records carry injected markup.

Each flag the system defines SHALL be shown to fire on the published export, or its absence SHALL be
established as a fact about the source rather than assumed from a zero count.

#### Scenario: A zero flag count is accounted for

- **WHEN** a run reports a parse flag with a count of zero
- **THEN** that zero has been confirmed against the source as a real absence, not left as evidence
  that the flag's condition was never reachable

### Requirement: Parse flags travel with the record

Flags SHALL be carried on the emitted record, not only aggregated in the report, so a downstream
reader can tell an exact measurement from a recovered or caveated one without re-running ingestion.

`parse_flags` SHALL be present on every emitted record as an array of strings, empty when nothing
was flagged — never absent. A consumer can then model it as one required field with a default and
read it the same way on every line, instead of distinguishing "clean" from "key missing".

#### Scenario: A caveated record in the corpus

- **WHEN** a record was flagged during cleaning
- **THEN** its emitted line carries those flags

#### Scenario: A clean record carries an empty list

- **WHEN** a record was not flagged during cleaning
- **THEN** its emitted line carries `parse_flags` as an empty array, not an absent key

### Requirement: The fused-range predicate is a field, not a naming convention

`parse_flags` is a reporting vocabulary, not a consumer interface. It carries fourteen names today,
of which eleven begin with `range_` and only three mean the stored bounds may fuse two unrelated
quantities: `range_plus_minus`, `range_mean_sd_embedded` and `range_percent_deviation` mark
*successful* parses, `range_is_link` and `no_scalar` mark rows with no scalar at all, and
`range_unparsed` marks a cell no number could be read from. Neither "non-empty `parse_flags`" nor a
`range_` prefix is therefore the predicate: over the export those rules select 13,016 and 8,055
records against the 1,418 meant, and would mark thousands of correctly-parsed entries as
untrustworthy in a user-visible marking — teaching a reader to ignore it, which is a worse outcome
than the defect being marked.

The system SHALL therefore emit a dedicated boolean field, `range_fused`, present on every record,
`true` when the stored `range_low`/`range_high` may fuse numbers that do not belong to one quantity
and `false` otherwise. This field, not any flag name, is the contract `add-ask-agent` consumes: it is
read directly, forwarded without interpretation, and unaffected by anything cleaning does inside
`parse_flags`.

#### Scenario: The kind of hedge is a field, not a flag name

- **WHEN** a record's stored bounds came from a one-sided bound or from an approximation marker
- **THEN** its line carries `range_one_sided` and `range_approximate` as boolean fields
- **AND** `range_qualified` is true exactly when one of those two is

The kind matters to a consumer, not only the fact: a one-sided bound and an approximation need
different words in front of a reader, and showing "bounded, not exact" for `~20` states something the
source did not. `add-ask-agent` read both kinds out of `parse_flags` by name until these fields
existed — so a rename here would have turned them silently false there, with its fallback wording
continuing to work, which is what would have hidden it.

The flag names remain internal to cleaning and MAY be renamed, split, merged or dropped as the corpus
is better understood; `range_fused` MUST continue to answer the same question when they do. Cleaning
SHALL NOT retire or redefine `range_fused` without a message to `add-ask-agent`.

#### Scenario: A clean record carries a false predicate

- **WHEN** a record was not flagged during cleaning
- **THEN** its emitted line carries `range_fused` as `false`, not an absent key

#### Scenario: A fused range is marked

- **WHEN** a range cell yielded more than two numbers, or prose stood between the two bounds used
- **THEN** the record carries `range_fused` as `true`
- **AND** the computed bounds are unchanged

#### Scenario: A flagged record whose range is not fused

- **WHEN** a record carries only flags that do not concern fusion — an uncertainty range parsed from
  a plus-or-minus cell, a recovered mean and deviation, a link-only row, or a cell no number could be
  read from
- **THEN** `range_fused` is `false`
- **AND** this holds even though `parse_flags` is non-empty and its entries begin with `range_`
