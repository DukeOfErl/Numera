## MODIFIED Requirements

### Requirement: The deterministic layer is logged under a per-question identifier

Searches, retrievals, alias resolutions, truncation decisions, and each spend increment SHALL be
recorded, and every record for one question SHALL carry the same identifier so the question's trail
can be reassembled.

Several failures here are silent rather than loud — an alias resolving to the wrong stored value, a
truncated result treated as complete, spend accumulated from a response that reported no cost — and a
non-deterministic agent reproduces them only sometimes. The identifier is what makes an intermittent
failure investigable after the fact.

Every record SHALL also carry the identifier of the session the question was asked in. The question
identifier locates one question; without the session, a sequence of questions asked by one person
cannot be reassembled, and one person asking ten questions is indistinguishable from ten people
asking one.

Records SHALL survive the process that wrote them, and SHALL be retained where a restart, a
redeployment or the replacement of the host does not discard them. "Investigable after the fact" is
the whole purpose above, and a record that lives only as long as its container satisfies the letter
of this requirement while defeating it: the failures it names are intermittent, so the run worth
investigating is almost never the run still in progress.

Where records are retained SHALL be configurable, and the system SHALL run unimpaired when no
durable destination is configured. A prototype on a developer's machine needs no such destination,
and refusing to start without one would make the absence of telemetry an outage.

#### Scenario: A question is answered
- **WHEN** a question completes
- **THEN** its searches, retrievals, and spend increments are recorded
- **AND** every record for that question carries the same identifier

#### Scenario: A search was truncated
- **WHEN** a search matched more entries than were returned
- **THEN** the record states how many matched and how many were returned

#### Scenario: Two questions run in one session
- **WHEN** two questions are answered in the same session
- **THEN** their records carry different identifiers

#### Scenario: Two questions in one session are related afterwards
- **WHEN** two questions are answered in the same session
- **THEN** their records carry the same session identifier
- **AND** the order in which the questions were asked can be recovered from the records alone

#### Scenario: The process that wrote the records is replaced
- **WHEN** the application is restarted, redeployed, or moved to another host
- **AND** a durable destination is configured
- **THEN** records written before the replacement remain readable afterwards

#### Scenario: No durable destination is configured
- **WHEN** no durable destination is configured
- **THEN** questions are answered exactly as they otherwise would be
- **AND** the absence is reported once, rather than on every question

## ADDED Requirements

### Requirement: Recording is best-effort and never fails a question

A failure to record SHALL NOT fail, delay or alter the question being answered. The system SHALL
answer the question and report the failure, never the reverse.

This is the deliberate opposite of the spend limits, and the contrast is the reason it is written
down. A spend limit fails closed because proceeding costs unbounded real money; recording fails open
because proceeding costs one row of a dataset that is read by eye. Both are a write that did not
happen, and the next reader will otherwise make them consistent with each other by analogy and get
one of them exactly wrong.

The refusal SHALL belong to the recording operation itself, not to its callers. A driver that
tolerates the failure protects only that driver, and the next caller — a harness, a test, a second
interface — inherits an operation that raises.

A failed write SHALL NOT be retried within the question. An unreachable destination does not fail
quickly, it hangs, and a question held open waiting to record a row is a worse outcome for the reader
than the missing row.

A failure SHALL be reported where an operator will see it, and SHALL NOT be reported to the person
asking the question. The hazard of failing open is not the lost row; it is discovering weeks later
that nothing was ever recorded. Silence toward the reader, noise toward the operator.

#### Scenario: The destination is unreachable
- **WHEN** a question is answered and the durable destination cannot be written to
- **THEN** the question is answered and its answer is shown unchanged
- **AND** the failure is reported to the operator
- **AND** nothing about the failure is shown to the person who asked

#### Scenario: The destination is slow
- **WHEN** a write to the durable destination does not complete promptly
- **THEN** the write is abandoned rather than retried
- **AND** the question is not held open waiting for it

#### Scenario: Something other than a driver records
- **WHEN** the recording operation is called directly rather than through an interface
- **AND** the destination cannot be written to
- **THEN** the caller is not required to handle an error to keep working

#### Scenario: Recording has been failing for some time
- **WHEN** writes to the durable destination have been failing
- **THEN** the number of failures is recoverable without reading a log line by line
