# agent-session Specification

## Purpose
Defines the boundary between the agent and whatever drives it: what the agent emits, what it
accepts, and what must survive being written to disk and read back in a different process. This is
what lets a terminal, a web application, and an unattended evaluation harness drive the same agent
without any of them being a special case inside it.
## Requirements
### Requirement: The agent communicates through events and commands only

The agent SHALL report its progress by emitting events, and SHALL accept input only as commands. It
SHALL NOT read from or write to any interface directly, and SHALL NOT block waiting for input.

A blocking call presumes a caller that can be blocked. A web interface that re-runs its script on
each interaction has no such caller, so an agent that waits on input cannot be driven by one.

#### Scenario: A question is answered
- **WHEN** a question is put to the agent as a command
- **THEN** it emits events as it works and an event carrying the answer
- **AND** it writes nothing to any interface itself

#### Scenario: The agent yields between turns
- **WHEN** a question is finished
- **THEN** the agent returns control to its driver
- **AND** it does not wait on any input channel for the next question

#### Scenario: The agent is driven by different interfaces
- **WHEN** the same question is put to the agent through different drivers
- **THEN** the sequence of events emitted is the same
- **AND** no driver requires behaviour from the agent that the others do not

### Requirement: Unattended operation is a driver, not a mode

The agent SHALL behave identically whether or not an interactive user is present. What to do with an
event — render it, log it, or act on it — is the driver's responsibility.

#### Scenario: A limit is reached under an unattended driver
- **WHEN** a question ends on a limit and no user is present
- **THEN** the driver records the outcome from the emitted events
- **AND** the agent's behaviour is the same as it would be with a user present

#### Scenario: The same question through an attended and an unattended driver
- **WHEN** the same question is put through an interactive driver and an unattended one
- **THEN** the events the agent emits are the same in both
- **AND** the agent is given no parameter indicating which driver is calling it

### Requirement: Events carry enough detail to show progress and to explain an ending

Events SHALL report retrieval as it happens, not only the final answer, so that a driver can show
what the agent is doing during a long question. An event ending a question SHALL carry why it ended
and, where a limit caused it, what had been spent or consumed.

#### Scenario: A question takes a long time
- **WHEN** the agent performs several retrievals before answering
- **THEN** an event is emitted for each retrieval, as it happens
- **AND** a driver can render progress without waiting for the answer

#### Scenario: A question ends on a limit
- **WHEN** a limit ends a question
- **THEN** the ending event names the limit and reports what had been consumed

### Requirement: Session state survives a process boundary

All state a session needs to continue SHALL be persisted as the session progresses. A session SHALL
be continuable by a process that did not create it, given only its identifier.

State kept in memory rather than in the persisted session is lost on redeploy, on restart, and
between web requests — and the loss is silent until someone tries to continue.

#### Scenario: Continuing after the original process has ended
- **WHEN** a question in a session has completed
- **AND** the process that created the session ends
- **AND** a new process continues that session by its identifier
- **THEN** a follow-up question is answered with the earlier conversation available to it

#### Scenario: Every kind of session state survives
- **WHEN** a session is continued in a new process
- **THEN** the conversation, the accumulated spend, and the ceiling in force are all present
- **AND** none of them has reset to its initial value

### Requirement: A transient failure does not end a question

WHERE a model call or a tool call fails for a transient reason — a rate limit, a gateway error, a
timeout — the system SHALL retry it before giving up, and SHALL end the question only once retries
are exhausted. A tool that raises SHALL return an error the agent can react to rather than ending the
run.

A question ended by a passing gateway error wastes whatever it had already spent, and in an
evaluation it consumes a question slot while measuring nothing.

#### Scenario: A model call fails transiently
- **WHEN** a model call fails for a transient reason
- **THEN** it is retried
- **AND** the question continues if a retry succeeds

#### Scenario: Retries are exhausted
- **WHEN** retries for a call are exhausted
- **THEN** the question ends
- **AND** the reason is reported as a provider failure rather than as an answer

#### Scenario: A tool raises
- **WHEN** a tool raises an exception
- **THEN** the agent receives an error result it can act on
- **AND** the run does not collapse

### Requirement: The deterministic layer is logged under a per-question identifier

Searches, retrievals, alias resolutions, truncation decisions, and each spend increment SHALL be
recorded, and every record for one question SHALL carry the same identifier so the question's trail
can be reassembled.

Several failures here are silent rather than loud — an alias resolving to the wrong stored value, a
truncated result treated as complete, spend accumulated from a response that reported no cost — and a
non-deterministic agent reproduces them only sometimes. The identifier is what makes an intermittent
failure investigable after the fact.

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

### Requirement: Sessions are isolated from one another

State SHALL NOT pass between sessions. A session SHALL see only its own conversation, its own
retrieved entries, and its own accumulated spend.

#### Scenario: Two sessions run at the same time
- **WHEN** two sessions are active concurrently
- **THEN** neither observes the other's conversation or retrieved entries
- **AND** spend accumulated in one is not counted against the other

#### Scenario: A session identifier is reused
- **WHEN** a session is continued with an identifier that already exists
- **THEN** it continues that session rather than starting a new one

### Requirement: Follow-up questions inherit the conversation

Within a session, a question SHALL have access to the preceding questions and answers, so that a
follow-up which depends on earlier context can be answered.

#### Scenario: A follow-up depends on the previous question
- **WHEN** a question is asked that omits a subject established earlier in the session, such as asking about a different organism after a question about cell size
- **THEN** the omitted subject is taken from the conversation
- **AND** the answer addresses the question as the user meant it

#### Scenario: A new session does not inherit
- **WHEN** the same follow-up is asked at the start of a new session
- **THEN** the missing context is not assumed
- **AND** the agent asks for it or reports the question as ambiguous

### Requirement: Citations in a follow-up stand on their own

Every answer SHALL identify the entries supporting it in full, and SHALL NOT rely on a citation
given in an earlier answer.

A conversation is read from the middle as often as from the beginning, and an exported or logged
answer carries none of its predecessors.

#### Scenario: A follow-up cites an entry already cited
- **WHEN** an answer rests on an entry cited earlier in the session
- **THEN** it identifies that entry again in full

#### Scenario: An answer is read on its own
- **WHEN** an answer is read without the rest of the session
- **THEN** every quantity in it can still be traced to an entry

### Requirement: Per-question limits reset within a session; run limits do not

The per-question spend ceiling SHALL reset for each new question in a session. Any limit that
applies to a run of questions SHALL persist across the questions in that run.

Without the reset, a long conversation would strangle itself as accumulated spend approached the
ceiling; without the persistence, a run-level limit would not bound anything.

#### Scenario: A second question is asked in a session
- **WHEN** a question completes and another is asked in the same session
- **THEN** the second question begins with a fresh per-question ceiling

#### Scenario: A run-level limit is in force
- **WHEN** several questions are asked within one run
- **THEN** their spend accumulates against the run limit

### Requirement: Conversation growth is bounded, and the bound is announced before it bites

The system SHALL bound how much accumulated conversation is carried into a request. It SHALL warn
the user as that bound is approached, and SHALL refuse further questions in the session once it is
reached rather than silently discarding context.

The bound SHALL be measured in the units of the hazard it guards against -- the size of the
conversation, not the number of turns in it. A turn count is a poor proxy: one retrieved entry's
payload spans 16 to 8,023 characters across the reference corpus, so the same number of turns is
anywhere from a few thousand tokens to well over a hundred thousand, and a bound set on turns fires
far too early in a cheap session and too late in an expensive one. Where the provider reports the
size of what it received, that figure SHALL be preferred; where it does not, the size SHALL be
counted rather than assumed to be zero, so the bound cannot become one that is never reached.

Retrieved entries are large and a session accumulates them without limit, so an unbounded session
eventually fails on context length partway through a question. Condensing the conversation
automatically is the better long-term answer but a worse first one: a summariser that quietly drops
the entry a later answer depended on produces a confident answer with a missing citation, which is
the failure this project exists to avoid. Warning and stopping is honest; see the proposal's
Deferred section.

#### Scenario: A session approaches the bound
- **WHEN** accumulated conversation approaches the bound
- **THEN** the user is warned, with an indication of how much room is left

#### Scenario: A session reaches the bound
- **WHEN** accumulated conversation has reached the bound and a further question is asked
- **THEN** the question is refused with an explanation
- **AND** the user is directed to start a new session

#### Scenario: A conversation whose size nobody has reported
- **WHEN** no measurement of the conversation's size is available from the provider
- **THEN** its size is counted locally rather than treated as zero

#### Scenario: Context is never silently dropped
- **WHEN** a question is answered
- **THEN** no earlier context has been discarded without the user being told

### Requirement: A retired configuration name stops the run and names its replacement

Where a configuration variable has been renamed or withdrawn, the system SHALL refuse to start,
reporting the retired name and what to set instead. It SHALL NOT ignore a retired name.

A renamed variable that is merely ignored is configuration that silently stops being read. Every
setting this system takes from the environment changes what a run does: a spend ceiling that no
longer binds, a run label that quietly becomes the default and mixes an evaluation's spend into a
person's, a corpus path that falls back to none. Each of those produces a run that looks like it is
working, which is worse than one that will not start.

The refusal SHALL be reported as misconfiguration a person can fix, not as a fault — the message is
the point, and a traceback buries it.

Where a variable was withdrawn rather than renamed, the refusal SHALL NOT describe it as a rename.
A limit whose meaning changed cannot have its value carried across: a threshold read as a ceiling
stops work below where it used to give notice, so telling the reader to move the value would tighten
their limit while appearing to preserve it.

#### Scenario: A renamed variable is set
- **WHEN** a run is started with a retired variable name present in the environment
- **THEN** the run does not start
- **AND** the message names both the retired variable and its replacement

#### Scenario: The refusal precedes every other reading of the environment
- **WHEN** the only retired variable set is the one naming the corpus, and no current name is set
- **THEN** the run is refused for the retired name
- **AND** it is not reported as a missing or unsupplied corpus

#### Scenario: A setting is read outside any driver
- **WHEN** a caller that is not one of the shipped drivers reads a configuration setting
- **THEN** a retired name present in the environment still refuses the run

#### Scenario: A withdrawn variable is set
- **WHEN** a run is started with a variable that was withdrawn rather than renamed
- **THEN** the run does not start
- **AND** the message does not instruct the reader to rename it

