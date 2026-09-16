## MODIFIED Requirements

### Requirement: The deterministic layer is logged under a per-question identifier

Searches, retrievals, alias resolutions, truncation decisions, and each spend increment SHALL be
recorded, and every record for one question SHALL carry the same identifier so the question's trail
can be reassembled.

The question as asked and the answer as given SHALL also be recorded. Without them the trail says
what was searched for and what it cost, and not what was wanted or what was said — so a judgement
about an answer, whether from a reader or from whoever reads the records later, names something that
cannot be read. A trail cannot be backfilled: records already written name a question whose words
were never kept anywhere.

The entries an answer was built on SHALL be recorded together, distinguishing those the answer cited
from those merely retrieved. Both are already recoverable by reassembling individual search and
retrieval records, which is the argument for recording them once, in the form the question actually
resolved to: a reader asking "what evidence stood behind this answer" should not have to reconstruct
it, and a reconstruction can disagree with what the answer was given.

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

**What is kept about a person, and why.** Recording the question keeps words somebody typed, and that
is a decision rather than a side effect of plumbing. What is kept is the question, the answer, and
the entries behind it — and, where identity is configured, the account that asked and the role it
held at the time, carried on every record and written when the record is written rather than looked
up afterwards. Where identity is not configured, records carry no account, as before. They are kept
because the judgements this system collects are unreadable without them, and they are read by
whoever operates the system in order to improve it. A reader SHALL be able to learn this from the
interface rather than by inspecting the records, and the statement SHALL name the account and the
role when they are kept.

Recording the question or the answer SHALL NOT change what the model is shown. These are records of a
question that has already been answered, not context for the next one.

Failure to record any of this SHALL follow the same policy as every other record here: it fails open,
never failing a question.

#### Scenario: A question is answered
- **WHEN** a question completes
- **THEN** its searches, retrievals, and spend increments are recorded
- **AND** the question as asked and the answer as given are recorded
- **AND** every record for that question carries the same identifier

#### Scenario: Two questions ask different things
- **WHEN** two different questions are answered
- **THEN** the recorded question text differs between them

#### Scenario: An answer rests on retrieved entries
- **WHEN** a question completes having retrieved entries
- **THEN** one record names the entries the answer cited and the entries it retrieved
- **AND** the two sets are distinguishable from each other

#### Scenario: A question ends without an answer
- **WHEN** a question ends without producing an answer
- **THEN** the question as asked is still recorded

#### Scenario: The records cannot be written
- **WHEN** the question or the answer cannot be recorded
- **THEN** the question is answered exactly as it otherwise would be
- **AND** no error reaches the person who asked

#### Scenario: A further question follows a recorded one
- **WHEN** a question has been recorded and another is asked in the same session
- **THEN** neither the recorded question nor the recorded answer appears in what the model is shown

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

#### Scenario: A signed-in reader's question is recorded
- **WHEN** identity is configured and an enrolled account asks a question
- **THEN** every record for that question carries the account and the role it held

#### Scenario: No identity is configured
- **WHEN** identity is not configured and a question is asked
- **THEN** its records carry no account, exactly as before
