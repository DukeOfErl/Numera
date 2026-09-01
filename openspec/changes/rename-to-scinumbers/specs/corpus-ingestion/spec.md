## MODIFIED Requirements

### Requirement: The output satisfies the ask agent's corpus contract

Every emitted line SHALL carry the keys the ask agent's corpus loader requires: `entry_id`,
`property`, `organism`, `units`, `value`, `range_low`, `range_high`, `reference`,
`reference_pubmed_id`, `measurement_method`, `comments`, `keywords`.

`entry_id` SHALL be a number.

The key names the source's own vocabulary for its identifier no more than any other key does: the
consumer is not named for one database, and a corpus produced from a second source would satisfy the
same contract. The ingester's internal names and its run report may keep the source's vocabulary,
which is a description of what was read rather than a contract with a reader.

`value` SHALL be a number or null. `range_low` and `range_high` SHALL each be a number or null.
`keywords` SHALL be a list of strings. Any additional keys the ingester emits SHALL be ignorable: a
consumer reading only the keys above SHALL be able to load the corpus.

#### Scenario: A corpus is loaded by the consumer
- **WHEN** the ask agent's loader reads a corpus this ingester produced
- **THEN** every record loads
- **AND** no key it requires is absent

#### Scenario: The identifier key
- **WHEN** a record is emitted
- **THEN** its identifier is carried under `entry_id` as a number
