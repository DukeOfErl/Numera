## Purpose

When the model's side of answering a question — its turns, its tool calls, what it was shown — is
sent to a hosted tracer, so that a run a reader rated down can be inspected; what a trace carries,
how it is found from a question or a rating, and what must never follow from the tracer being there.

## ADDED Requirements

### Requirement: Hosted tracing is off unless this project's own setting turns it on

Nothing about answering a question SHALL be sent to a hosted tracer unless a setting named by this
project enables it. The tracer's credentials being present SHALL NOT enable it on their own: a key
left in a shell, a secrets box or a copied configuration is not a decision to send prompts, tool
results and corpus text to a third party, and that decision is what this setting records.

A setting whose value is not one this project recognises SHALL leave tracing off, and the operator
SHALL be told which value was not recognised. Off is the cheap direction for a mistyped setting: the
cost is a missing trace, and the alternative is data leaving the host on a value nobody wrote on
purpose.

A setting that enables tracing without the credentials it needs SHALL leave tracing off, SHALL tell
the operator what is missing, and SHALL NOT prevent any question from being answered.

#### Scenario: The setting is absent
- **WHEN** a question is answered and the project's tracing setting is not set
- **THEN** nothing about the question is sent to any hosted tracer

#### Scenario: The tracer's credentials are present but the setting is not
- **WHEN** the hosted tracer's credentials are configured and the project's tracing setting is not set
- **THEN** nothing about the question is sent to any hosted tracer

#### Scenario: The setting names something unrecognised
- **WHEN** the project's tracing setting holds a value this project does not recognise
- **THEN** nothing is sent to any hosted tracer
- **AND** the operator is told the value was not recognised
- **AND** questions are answered as they would be with the setting absent

#### Scenario: The setting enables tracing but a credential is missing
- **WHEN** the project's tracing setting enables tracing and a credential it needs is absent
- **THEN** nothing is sent to any hosted tracer
- **AND** the operator is told which credential is missing
- **AND** questions are answered as they would be with the setting absent

### Requirement: A tracing vendor's own switch does not send anything

A tracing vendor's environment switch that would otherwise enable tracing of the framework the agent
is built on SHALL NOT cause anything about a question to be sent, whether or not this project's own
setting enables tracing. The refusal SHALL hold for every way a question can be asked — the web
page, the terminal, the evaluation harness, and a caller that constructs the agent directly — because
it belongs to answering a question rather than to any one of the programs that asks.

#### Scenario: The framework vendor's switch is set and the project's setting is not
- **WHEN** the environment enables the framework vendor's tracing and the project's tracing setting is not set
- **THEN** nothing about the question is sent to that vendor or to any other hosted tracer

#### Scenario: The framework vendor's switch is set beside the project's setting
- **WHEN** the environment enables the framework vendor's tracing and the project's setting enables the chosen tracer
- **THEN** the question is traced only by the tracer the project's setting chose

#### Scenario: A caller builds the agent directly
- **WHEN** a question is asked through the agent by a caller other than the shipped programs, with the framework vendor's switch set
- **THEN** nothing about the question is sent to that vendor

### Requirement: One question is one trace, found by the question's identifier

With tracing on, each question SHALL produce exactly one trace, and that trace SHALL be locatable
from the question's identifier alone — the same identifier the trail and any rating already carry —
without consulting any table that maps one to the other. A mapping kept somewhere is a mapping that
can be lost, and without it a rating names a question whose trace cannot be found.

The trace SHALL carry the question's identifier, the session it was asked in, and the run label the
trail records, so a trace can be filtered to one session and an evaluation run told apart from a
person's questions.

#### Scenario: A question is answered with tracing on
- **WHEN** a question is answered with tracing on
- **THEN** exactly one trace is produced for it
- **AND** its identifier can be computed from the question's identifier alone
- **AND** it carries the question's identifier, the session and the run label

#### Scenario: Two questions in one session
- **WHEN** two questions are asked in the same session with tracing on
- **THEN** they produce two traces with different identifiers
- **AND** both carry the same session

### Requirement: A trace names who asked only by an opaque value, and the agent is still not told

A trace of a question asked by a signed-in reader SHALL carry a value that is the same for every
question that account asks and different between accounts, and SHALL NOT carry the reader's address,
name or role. The tracer is a third party, and attribution needs a stable key, not a person.

Where nobody is signed in — no sign-in configured, the terminal, the evaluation harness — a trace
SHALL carry no such value, rather than a placeholder that reads as an account.

Attaching that value SHALL NOT change what the agent is handed. The agent SHALL receive the same
inputs for a question whoever asks it and whether tracing is on or off, as `user-identity` already
requires.

#### Scenario: A signed-in reader asks two questions
- **WHEN** a signed-in reader asks two questions with tracing on
- **THEN** both traces carry the same per-account value
- **AND** neither carries the reader's address, name or role

#### Scenario: Two readers ask
- **WHEN** two different signed-in readers each ask a question with tracing on
- **THEN** their traces carry different per-account values

#### Scenario: Nobody is signed in
- **WHEN** a question is asked with tracing on and no reader is signed in
- **THEN** its trace carries no per-account value

#### Scenario: The agent's inputs do not depend on tracing or on the reader
- **WHEN** the same question is asked by two different readers, once with tracing on and once with it off
- **THEN** what the agent is given is the same in every case

### Requirement: A rating is copied to its question's trace, and the trail remains the record

With tracing on, a rating recorded under `answer-feedback` SHALL also be sent to the trace of the
question it rates, carrying the verdict, and a comment SHALL be sent to the same trace when one is
given. The copy SHALL NOT replace, delay or condition the rating's record in the trail: the trail is
where ratings are read back from, and a copy that fails SHALL leave that record exactly as it would
otherwise have been.

The copy SHALL be sendable before the trace itself has arrived at the tracer, since a reader can
rate an answer while the tracer is still receiving it.

#### Scenario: A reader rates an answer with tracing on
- **WHEN** a reader rates an answer with tracing on
- **THEN** the rating is recorded in the trail as `answer-feedback` requires
- **AND** the verdict is sent to the trace of the question it rates

#### Scenario: A reader adds a comment
- **WHEN** a reader adds a comment to a rating with tracing on
- **THEN** the comment is recorded in the trail
- **AND** it is sent to the same trace as the verdict

#### Scenario: The copy cannot be sent
- **WHEN** a reader rates an answer and the tracer cannot receive the copy
- **THEN** the rating is recorded in the trail exactly as it would otherwise have been
- **AND** the reader is shown nothing different

#### Scenario: Tracing is off
- **WHEN** a reader rates an answer with tracing off
- **THEN** nothing is sent to any hosted tracer

### Requirement: A tracer fault never reaches a reader

A hosted tracer that is unreachable, that rejects what it is sent — including because a usage
allowance is exhausted — or whose client raises, SHALL NOT change the answer given, the entries
shown, the trail's records, a rating's record, or the time a reader waits beyond what is already
bounded for recording. It SHALL NOT be shown to the reader. The operator SHALL be able to learn that
tracing is failing.

This is the line the trail already draws: a trace is a debugging aid, and the cost of a lost trace is
one trace, while the cost of a tracer that can fail a question is a reader blocked by telemetry.

#### Scenario: The tracer is unreachable
- **WHEN** a question is answered with tracing on and the tracer cannot be reached
- **THEN** the answer and the entries shown are the same as with tracing off
- **AND** the trail's records for the question are the same as with tracing off
- **AND** the reader is shown no error about tracing

#### Scenario: The tracer's client raises
- **WHEN** the tracer's client raises while a question is being answered
- **THEN** the question is answered as it would be with tracing off
- **AND** the operator can see that tracing failed
