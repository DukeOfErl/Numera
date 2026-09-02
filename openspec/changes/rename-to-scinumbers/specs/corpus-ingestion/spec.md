## MODIFIED Requirements

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
