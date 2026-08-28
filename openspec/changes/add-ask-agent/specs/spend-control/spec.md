## Purpose

Bounds what questions may cost, and stops the agent rather than trusting it to stop itself. An agent
decides its own number of steps, so without an enforced ceiling the cost of a question is unbounded
by construction — and the user finds out afterwards.

These limits are a development-stage guard. The eventual answer is a provider-side spend cap on the
key itself, or users supplying their own key; see the proposal's Deferred section.

## ADDED Requirements

### Requirement: Spend is taken from what the provider reports

Accumulated spend SHALL be read from the cost the provider reports for each request where the
provider reports one. WHERE it does not, spend SHALL be computed from reported token usage priced by
configured per-token rates, and the system SHALL refuse to run against a model for which neither a
reported cost nor configured prices are available.

Reported cost is the provider's own figure: it needs no price table to keep current, does not drift
when the provider reprices, and accounts for cache reads and writes without the system modelling
them. A local price table is a fallback, not the primary mechanism.

Monetary amounts SHALL be held as integer minor units so that repeated addition introduces no
rounding drift.

#### Scenario: The provider reports a cost
- **WHEN** a response carries the provider's cost for that request
- **THEN** that figure is added to accumulated spend
- **AND** no local price table is consulted

#### Scenario: The provider reports usage but no cost
- **WHEN** a response carries token usage but no cost
- **THEN** spend is computed from that usage and the configured prices for the model

#### Scenario: Neither cost nor prices are available
- **WHEN** a model reports no cost and has no configured prices
- **THEN** the system stops with a message naming the model
- **AND** no request is dispatched

#### Scenario: A retried request
- **WHEN** a request is retried after a transient failure
- **THEN** every attempt that the provider billed is accumulated
- **AND** retries are bounded by the same ceiling as any other spend

#### Scenario: A streamed response
- **WHEN** a response is streamed
- **THEN** the cost reported at the end of the stream is accumulated

### Requirement: A pre-request gate stops work before the ceiling is crossed

Before dispatching each model request, the system SHALL compare accumulated spend against the
ceiling and SHALL NOT dispatch the request when the ceiling has been reached. Enforcement SHALL live
in the code that issues requests, not in instructions given to the model.

An instruction to stay within budget is a preference the model may or may not honour. A gate in the
dispatch path is a limit. Only the second is a control.

#### Scenario: Accumulated spend is below the ceiling
- **WHEN** the next model request is about to be dispatched
- **AND** accumulated spend is below the ceiling
- **THEN** the request proceeds

#### Scenario: Accumulated spend has reached the ceiling
- **WHEN** the next model request is about to be dispatched
- **AND** accumulated spend has reached the ceiling
- **THEN** the request is not dispatched
- **AND** the question ends

#### Scenario: Reported spend exceeds the ceiling
- **WHEN** the request that crossed the ceiling has completed
- **THEN** final spend for the question may exceed the ceiling by at most that one request
- **AND** the reported figure is the actual spend, not the ceiling

### Requirement: A configurable ceiling, with the warning derived from it

The system SHALL carry a configurable per-question **ceiling**, defaulting to USD 0.60, and SHALL
derive the warning threshold as 80 per cent of it. The configured number SHALL be the one that stops
work, so that a reader of the configuration can see the limit that binds. The ceiling SHALL be
changeable without code changes.

A retired setting that named the warning instead SHALL be refused with its replacement named, rather
than read under the new meaning: the same number carried over would silently tighten the hard limit
to 80 per cent of what it used to permit, and a spend limit that quietly tightens is worse than one
that will not start.

#### Scenario: Spend passes the warning threshold
- **WHEN** accumulated spend passes 80 per cent of the ceiling
- **THEN** the user is told the question has become expensive and what has been spent
- **AND** work continues

#### Scenario: Spend reaches the hard ceiling
- **WHEN** accumulated spend reaches the ceiling
- **THEN** the question ends

#### Scenario: The ceiling is reconfigured
- **WHEN** the ceiling is set to a different amount
- **THEN** the warning threshold is recomputed as 80 per cent of that amount

#### Scenario: The retired setting is supplied
- **WHEN** the environment carries the setting that used to name the warning threshold
- **THEN** the run refuses to start and the message names the setting to use instead

### Requirement: An answer that ran to its ceiling says so

The gate decides before dispatching and cannot decide after, since a request's cost is unknown until
it returns. A question may therefore answer with spend at or past its ceiling, having simply not
needed another request. That is a different thing from a question that finished with room to spare,
and the system SHALL distinguish them.

WHEN a question ends, the system SHALL report the ceiling it ran against, and SHALL mark an answer
whose spend reached that ceiling. The mark SHALL appear only where the ceiling was reached, and not
on an ending that already names the ceiling as its reason.

#### Scenario: An answer produced with room to spare
- **WHEN** a question answers having spent less than its ceiling
- **THEN** the ending says nothing about the ceiling

#### Scenario: An answer produced at the ceiling
- **WHEN** a question answers having spent at or past its ceiling
- **THEN** the ending reports that it ran to the ceiling, and names the figure

### Requirement: A question ended on the ceiling reports what it established

WHEN a question ends because its ceiling was reached, the system SHALL present whatever was
established before it stopped, with citations, marked as incomplete. The question SHALL NOT be
discarded, and the ending SHALL be reported as a spend outcome rather than as an answer.

#### Scenario: A question ends on its ceiling
- **WHEN** the ceiling ends a question
- **THEN** the partial findings are presented with their citations
- **AND** the answer is marked incomplete
- **AND** the ending is recorded as having been caused by the ceiling

#### Scenario: A later question in the same session
- **WHEN** a question has ended on its ceiling and another is asked in the same session
- **THEN** the new question begins with a fresh per-question ceiling

### Requirement: A run of questions carries its own budget

The system SHALL bound the total spend of a run of questions independently of the per-question
ceiling, defaulting to USD 1.20 and configurable. Spend SHALL accumulate against the run budget
across every question in the run, and the run SHALL stop when the budget is reached.

The per-question ceiling bounds one question; without a run budget, a run of fifty questions is
bounded only by their number. The run budget is the figure that determines what an evaluation can
cost, which is where an unbounded agent does the most damage.

A run is not a session. Run spend SHALL be accumulated against the run, and SHALL be reachable from
any session belonging to it, so a driver that opens a session per question is bounded by one figure
rather than by none. Spend accumulated by one run SHALL NOT be charged to another sharing the same
storage. It SHALL be recorded as each charge is made rather than when a question ends, so a question
that ends by raising has still been counted -- otherwise a crash loop is free.

#### Scenario: A run stays within budget
- **WHEN** questions complete and accumulated run spend remains below the budget
- **THEN** the run proceeds to the next question

#### Scenario: A run reaches its budget
- **WHEN** accumulated run spend reaches the run budget
- **THEN** no further question is begun
- **AND** the run stops with its progress preserved

#### Scenario: A budget spent in one session stops the next
- **WHEN** a run's budget is reached and a question is asked in a different session of the same run
- **THEN** that question is refused before any model call

#### Scenario: Two runs share one store
- **WHEN** two runs record spend against the same storage
- **THEN** each run's total counts only its own questions

#### Scenario: Budget is reconfigured
- **WHEN** the run budget is set to a different amount
- **THEN** the new amount bounds subsequent runs

### Requirement: A run stopped on budget is distinguishable from a completed run

WHERE a run stops because its budget was reached, the report SHALL say so, SHALL state how many
questions of the intended set were attempted, and SHALL state how many of them ended on the
per-question ceiling.

At the default settings, two questions that each run to the per-question ceiling exhaust the run
budget. That is intended — it stops a systematic fault early — but a report that does not
distinguish it from a finished run presents a tripped circuit breaker as a poor score.

#### Scenario: A run stops on its budget
- **WHEN** a run ends because the run budget was reached
- **THEN** the report states that the run stopped on budget
- **AND** states how many questions were attempted out of the intended set
- **AND** states how many questions ended on the per-question ceiling

#### Scenario: A run finishes normally
- **WHEN** every intended question has been attempted within budget
- **THEN** the report states that the run completed

### Requirement: Spend state persists across processes

Accumulated run spend and the per-question ceiling in force SHALL both be persisted, and SHALL
survive the process that recorded them.

Spend that lives only in memory restarts at zero when work resumes in another process, which
silently doubles what it may cost. The two are persisted against different things on purpose: the
ceiling belongs to the session, because the ceiling a session was created with is the one it keeps,
while spend belongs to the run, because that is what the budget bounds.

#### Scenario: A session resumes
- **WHEN** a suspended session is resumed, in the same process or another
- **THEN** accumulated spend continues from its persisted value rather than restarting at zero
- **AND** the ceiling in force is the one the session was created with

#### Scenario: Spend across a session's questions
- **WHEN** several questions are asked in one session
- **THEN** each question's spend is recorded against that question
- **AND** the session's total is the sum of them

The two limits SHALL therefore differ in what reconfiguring them reaches, and the difference is
deliberate rather than incidental. A ceiling is fixed when a session is created, so a conversation
already under way cannot be handed a larger one by changing the environment between two processes.
A budget bounds a run and remains the operator's to move, because a run stopped on budget is told to
raise it — a promise made in words that the behaviour has to keep. Raising a budget SHALL release a
run stopped on it, and SHALL NOT forgive the spend already made, which counts against the new figure.

#### Scenario: A budget is raised for a stopped run
- **WHEN** a run stopped on its budget is resumed under a larger one
- **THEN** questions are accepted again
- **AND** the spend already accumulated counts against the new budget

#### Scenario: A ceiling is raised for an existing session
- **WHEN** a session is resumed under a larger configured ceiling
- **THEN** the session keeps the ceiling it was created with

### Requirement: An expensive question is flagged before work begins

Before beginning work on a question, the system SHALL project its cost from the retrieval the
question is expected to require, and SHALL tell the user before proceeding when that projection
exceeds the warning threshold. The projection SHALL be presented as an estimate and SHALL NOT be
used for enforcement.

#### Scenario: Projection exceeds the warning threshold
- **WHEN** a question is projected to cost more than the warning threshold
- **THEN** the user is told the estimate before work begins

#### Scenario: Projection proves wrong
- **WHEN** actual spend diverges from the projection
- **THEN** the gate acts on measured spend
- **AND** the projection has no effect on where work stops

### Requirement: Spend is always reported

Every answer SHALL report what it cost, whether it completed or ended on a limit, and SHALL name the
model that incurred it.

Spend is only interpretable next to the model that produced it: the same question costs very
different amounts on a cheap development model and a capable one.

#### Scenario: A question completes
- **WHEN** an answer is returned
- **THEN** the spend for that question and the model used are reported with it

#### Scenario: A question is abandoned
- **WHEN** a question ends without an answer
- **THEN** the spend incurred before it ended is still reported
