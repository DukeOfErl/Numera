## Purpose

Defines the boundary between the agent and whatever drives it: what the agent emits, what it
accepts, and what must survive being written to disk and read back in a different process. This is
what lets a terminal, a web application, and an unattended evaluation harness drive the same agent
without any of them being a special case inside it.

## ADDED Requirements

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

#### Scenario: Inspecting the agent for an unattended mode
- **WHEN** the agent's behaviour is examined
- **THEN** it carries no setting that distinguishes attended from unattended operation

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

#### Scenario: State that cannot be persisted
- **WHEN** any state a session needs to continue cannot be written to the session
- **THEN** this is a defect, not a limitation of the driver

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

#### Scenario: Context is never silently dropped
- **WHEN** a question is answered
- **THEN** no earlier context has been discarded without the user being told
