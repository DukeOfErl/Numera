## Purpose

Scores the agent's answers against a held-out set of questions whose supporting entries are known.
The agent is non-deterministic, so evaluation has to measure a distribution rather than check a
single run — this is the only way to tell an improvement from a lucky trajectory.

## ADDED Requirements

### Requirement: The question set is explicit and versioned with its answers

The evaluation SHALL read a question set in which each question records the entry identifiers that
should support its answer, and SHALL fail with an explanatory message when no question set is
supplied. Question sets SHALL NOT be generated at evaluation time by the system under test.

#### Scenario: Question set supplied
- **WHEN** the evaluation runs with a question set
- **THEN** each question is asked and scored against its recorded supporting entries

#### Scenario: No question set supplied
- **WHEN** the evaluation runs without one
- **THEN** it stops with a message explaining that a question set is required

### Requirement: Scoring is based on cited entries, not answer text

The evaluation SHALL score an answer by comparing the entry identifiers it cited against those
recorded for the question, reporting how many expected entries were cited and how many cited
entries were not expected. It SHALL NOT score by string comparison of the answer prose.

#### Scenario: Answer cites the expected entries
- **WHEN** an answer cites every entry recorded for the question
- **THEN** it is scored as citing all expected entries

#### Scenario: Answer cites unexpected entries
- **WHEN** an answer cites entries not recorded for the question
- **THEN** those are reported separately rather than counted as errors, since the corpus may support the answer through entries the question set does not list

### Requirement: Unsupported questions are part of the set

The question set SHALL include questions the corpus cannot answer, and the evaluation SHALL score
whether the agent declined them rather than producing a quantity.

A system that answers everything scores well on questions with answers and is worthless in
practice; the refusal behaviour is a capability under test, not an edge case.

#### Scenario: Agent declines an unanswerable question
- **WHEN** a question recorded as unsupported is asked
- **AND** the answer states no quantity
- **THEN** it is scored as correctly declined

#### Scenario: Agent answers an unanswerable question
- **WHEN** a question recorded as unsupported is asked
- **AND** the answer states a quantity
- **THEN** it is scored as a fabrication and reported separately from citation failures

### Requirement: Run-to-run variation is measured, not averaged away

The evaluation SHALL support asking each question more than once and SHALL report the variation
across runs alongside the aggregate, rather than reporting a single run's figure as the result.

#### Scenario: A question is asked multiple times
- **WHEN** the evaluation runs each question more than once
- **THEN** the report gives the aggregate and the spread across runs

#### Scenario: A question answers inconsistently
- **WHEN** the same question yields different cited entries across runs
- **THEN** that question is reported as unstable

### Requirement: Results are recorded as each question completes

The evaluation SHALL append each question's result as that question finishes, rather than holding
results until the run ends. A run interrupted for any reason SHALL leave the results of every
question completed before the interruption.

#### Scenario: A run is interrupted
- **WHEN** a run stops before attempting every question — on its budget, on an error, or by the user
- **THEN** the results of every completed question are on disk
- **AND** no completed result is lost

#### Scenario: A question fails
- **WHEN** one question fails
- **THEN** its failure is recorded
- **AND** the run continues to the next question

### Requirement: An interrupted run resumes without repeating work

The evaluation SHALL be able to resume against an existing results file, attempting only the
questions and repeats not already recorded. Resuming SHALL NOT re-run a question whose result is
already present.

Because questions are scored independently, resumption is defined per question. A question
interrupted midway is re-attempted from the start; at the per-question ceiling, the most that can be
lost is one question's spend.

#### Scenario: Resuming a partial run
- **WHEN** a run resumes against a results file holding some questions
- **THEN** only the missing questions and repeats are attempted
- **AND** the recorded results are left as they are

#### Scenario: Spend across a resumed run
- **WHEN** a run resumes
- **THEN** the report distinguishes spend incurred in this session from total spend across all sessions of the run

### Requirement: A report can be produced from a partial results file

The evaluation SHALL produce its report from the recorded results, and SHALL do so whether the run
finished or not. A report over a partial file SHALL state how many questions of the intended set it
covers.

#### Scenario: Reporting mid-run
- **WHEN** a report is produced from a results file for a run still in progress or stopped early
- **THEN** the report is produced from the results present
- **AND** it states how many of the intended questions those results cover

#### Scenario: Partial results are not presented as complete
- **WHEN** a report covers fewer questions than intended
- **THEN** it does not present its figures as covering the full set

### Requirement: Recorded results are usable by external evaluation tools

Each recorded result SHALL carry the question as asked, the answer produced, the entries cited, and
the entries expected, in a form that can be read by evaluation tooling other than this project's own
reporter.

Retrofitting this shape later would mean re-running the evaluation to regenerate every record, so
the cost of adopting an external tool would be paid in model spend rather than in code.

#### Scenario: A result is recorded
- **WHEN** a question's result is written
- **THEN** it carries the question, the answer, the cited entries, the expected entries, and the model used

#### Scenario: Results are read by another tool
- **WHEN** a results file is read by evaluation tooling that is not this project's reporter
- **THEN** each record supplies the question, the answer, the retrieved context, and the expected result without transformation

### Requirement: Every result records the model that produced it

Each recorded result SHALL name the model that produced the answer, and every report SHALL state the
model or models its figures came from. A report covering results from more than one model SHALL
break its figures down by model rather than combining them.

Without this, a baseline taken on a cheap development model is silently compared against one taken on
a capable model, and a change of model reads as a change in quality. It also separates the two
explanations for a failed citation requirement — a defective harness, or a model not strong enough to
follow it — which are otherwise indistinguishable from the score alone.

#### Scenario: A result is recorded
- **WHEN** a question's result is written
- **THEN** it names the model that produced the answer

#### Scenario: A report covers one model
- **WHEN** every result in a report came from the same model
- **THEN** the report names that model alongside its figures

#### Scenario: A report covers several models
- **WHEN** results from more than one model are present
- **THEN** the figures are reported per model
- **AND** no figure combines results across models

### Requirement: Cost and effort are reported

Each evaluation run SHALL report the model cost it incurred and the number of tool calls made, so
that a change improving accuracy at several times the cost is visible as such.

#### Scenario: An evaluation run completes
- **WHEN** a run finishes
- **THEN** the report states the model cost and the total tool calls
- **AND** states them per question as well as in aggregate
