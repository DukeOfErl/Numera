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

Whatever the agent had established before the refusal SHALL be presented, with the ending marked
incomplete. Only where nothing was established SHALL the agent substitute a statement of its own, and
that statement SHALL report what happened without asserting who owns the key or who can raise its
limit — facts about a deployment rather than about the run.

Every driver SHALL tell the reader that the remedy lies with whoever pays for the deployment, in one
shared wording, and SHALL NOT offer advice that cannot help — a new session reaches the same refusal
on its first question.

Judgements about an answer's prose — an unsupported citation, an answer not grounded in the corpus —
SHALL apply only to text the reader was shown, and SHALL NOT be made about a statement the agent
substituted. Evidence of what retrieval found is not such a judgement and SHALL still be reported.

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
- **AND** the reader is told that the remedy lies with whoever pays for the deployment
- **AND** no further question is accepted in that session until the limit is raised

#### Scenario: The refusal arrives part-way through a question
- **WHEN** the agent has already established something citable and the provider then refuses for credit
- **THEN** what it established is presented rather than discarded
- **AND** the ending is marked incomplete
- **AND** the entries retrieved before the refusal are still reported

#### Scenario: Nothing was established before the refusal
- **WHEN** the provider refuses for credit before the agent has produced any answer text
- **THEN** the agent's own statement of what happened stands in for the answer
- **AND** no judgement about an answer's citations or grounding is reported, there being no answer to judge

#### Scenario: A credit refusal is not retried
- **WHEN** the provider refuses a request for lack of credit
- **THEN** the request is not attempted again
- **AND** the ending is reported without waiting out a retry delay

#### Scenario: A transient provider error is not mistaken for a spent key
- **WHEN** the provider fails for a reason other than credit
- **THEN** the question ends as an ordinary provider failure
- **AND** further questions are still accepted
