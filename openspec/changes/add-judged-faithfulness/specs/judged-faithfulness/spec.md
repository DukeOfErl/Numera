# judged-faithfulness

## Purpose

A second scoring layer over a recorded evaluation: a model separates an answer into claims and
judges each against the context the agent was shown. It is secondary to the identifier scoring
by decision (ADR-0510), and it is deferred out of `add-answer-evaluation` because the reference
it must be validated against was measured there and cannot support the gate — see the proposal.

## ADDED Requirements

### Requirement: Faithfulness is judged per claim, with a reason

When a judge is configured, the evaluation SHALL judge each answer that states a quantity by
separating it into claims and judging each claim against the recorded context, and SHALL record for
each claim its verdict and the judge's reason. A faithfulness score for the answer SHALL be derived
from the claim verdicts. An answer that states no quantity SHALL be recorded as not judged rather
than given a score.

The reason is the point of this layer, not the score: the identifier scoring already says that an
answer cited the wrong entry, and what it cannot say is that a right citation sits beside a wrong
number. A reason names the claim, which is what a user can be warned with and what a developer can
fix from.

#### Scenario: A claim is not supported by the context
- **WHEN** a judged answer contains a claim the recorded context does not support
- **THEN** the result records that claim, an unsupported verdict, and the judge's reason

#### Scenario: Every claim is supported
- **WHEN** every claim in a judged answer is supported by the recorded context
- **THEN** the answer's faithfulness score is the maximum
- **AND** no claim is reported as unsupported

#### Scenario: A refusal is not judged
- **WHEN** an answer states no quantity
- **THEN** it is recorded as not judged for faithfulness
- **AND** it does not contribute to the faithfulness aggregate

### Requirement: The judged layer is secondary and optional

The evaluation SHALL run and produce its full report with no judge configured. When a judge is
configured, the identifier and refusal scores SHALL be reported unchanged, and the judged figures
SHALL be reported beside them and SHALL NOT be combined with them into a single figure.

#### Scenario: No judge configured
- **WHEN** the evaluation runs without a judge
- **THEN** every result is recorded and the report is produced from the identifier and refusal scores

#### Scenario: A judge is configured
- **WHEN** the evaluation runs with a judge
- **THEN** the report gives the identifier and refusal figures as it would without one
- **AND** gives the judged figures separately

### Requirement: A judge is trusted only after measured agreement

The evaluation SHALL measure the agreement between the judge's verdicts and the identifier and
refusal scoring on every result where both can speak, SHALL list each disagreement for reading, and
SHALL mark the judged figures as not yet validated while the agreement is below a stated floor. A
judge finding an answer faithful where the refusal scoring recorded a fabrication SHALL be reported
as a judge miss.

The deterministic scoring is the reference against which the judge is validated, not the other way
round; a judge's verdicts are known to move under pushback and a disagreement is only informative
once the judge has been shown to agree where it must.

#### Scenario: Agreement below the floor
- **WHEN** the measured agreement is below the stated floor
- **THEN** the report marks the judged figures as not yet validated
- **AND** lists every disagreement

#### Scenario: The judge misses a fabrication
- **WHEN** the refusal scoring records a fabrication and the judge finds the same answer faithful
- **THEN** that result is reported as a judge miss

#### Scenario: The judge disagrees where it adds information
- **WHEN** the identifier scoring finds every cited entry expected and the judge finds a claim unsupported
- **THEN** that result is listed as a disagreement with the claim and reason, not counted as a judge miss

### Requirement: Every judgement records the judge model and its cost

Each recorded judgement SHALL name the model that produced it, the report SHALL break judged figures
down per judge model, and the judge's spend SHALL be reported separately from the agent's spend.

#### Scenario: A judgement is recorded
- **WHEN** a claim's verdict is written
- **THEN** it names the judge model that produced it

#### Scenario: Judgements from several judge models
- **WHEN** a report covers judgements from more than one judge model
- **THEN** the judged figures are reported per judge model
- **AND** no judged figure combines them

#### Scenario: A run with a judge completes
- **WHEN** a run with a judge configured finishes
- **THEN** the report states the judge's spend apart from the agent's
