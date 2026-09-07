## Purpose

Extends spend control to the limit this project does not enforce itself: the one on the key. Every
other bound here is the app's own — a per-question ceiling, a run budget, a conversation bound — and
each is reported by the component that enforces it. A provider's spending cap is enforced elsewhere
and arrives as a refused request, so the requirement is about *recognising* a limit rather than
imposing one.

An `ADDED` block rather than a modification: nothing already written changes meaning. This is the
ending that did not exist.

## ADDED Requirements

### Requirement: A refused-for-credit request ends the question as a limit, not a failure

Where the provider refuses a request because the key or account funding it has no credit left, the
agent SHALL end the question with a reason distinct from a transient provider failure, and that
reason SHALL be one after which no further question is accepted.

The ending SHALL be accompanied by an answer stating that a usage limit was reached, that the reader's
question was not at fault, and that the remedy lies with whoever pays for the deployment.

The agent SHALL NOT retry such a request. Retrying cannot succeed — a key acquires no balance during
a backoff — and it delays the only sentence the reader can act on.

Recognition SHALL rest on the status the provider reports and SHALL NOT depend on the wording of its
message, which the provider may change without notice.

Where a failure is not unambiguously a credit refusal, it SHALL remain an ordinary provider failure.
A transient error reported as a spent key would close the run for every reader on a reason that was
not true, while a spent key reported as a transient error costs one further attempt that says the
same thing again.

#### Scenario: The key funding a deployment reaches its cap
- **WHEN** the provider refuses a request because the funding key has no credit left
- **THEN** the question ends with a reason naming a limit rather than a failure
- **AND** an answer states what stopped, that the question was not at fault, and what would restart it
- **AND** no further question is accepted until the limit is raised

#### Scenario: A credit refusal is not retried
- **WHEN** the provider refuses a request for lack of credit
- **THEN** the request is not attempted again
- **AND** the ending is reported without waiting out a retry delay

#### Scenario: A transient provider error is not mistaken for a spent key
- **WHEN** the provider fails for a reason other than credit
- **THEN** the question ends as an ordinary provider failure
- **AND** further questions are still accepted
