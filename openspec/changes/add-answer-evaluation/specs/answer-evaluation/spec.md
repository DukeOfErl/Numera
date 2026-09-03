## Purpose

Scores the agent's answers against a held-out set of questions whose supporting entries are known.
The agent is non-deterministic, so evaluation has to measure a distribution rather than check a
single run — this is the only way to tell an improvement from a lucky trajectory.

## ADDED Requirements

### Requirement: The question set is explicit and versioned with its answers

The evaluation SHALL read a question set in which each question records the entry identifiers that
should support its answer, and SHALL fail with an explanatory message when no question set is
supplied. Question sets SHALL NOT be generated at evaluation time by the system under test.

Each question MAY carry tags naming what it exercises — a comparison across entries, a conversion,
an unsupported question, a follow-up — and the report SHALL be able to give its figures per tag, so
that a change which helps one kind of question and harms another is visible as both.

#### Scenario: Question set supplied
- **WHEN** the evaluation runs with a question set
- **THEN** each question is asked and scored against its recorded supporting entries

#### Scenario: No question set supplied
- **WHEN** the evaluation runs without one
- **THEN** it stops with a message explaining that a question set is required

#### Scenario: Figures per tag
- **WHEN** questions in the set carry tags
- **THEN** the report can give every figure for the questions carrying a given tag

### Requirement: Scoring is based on cited entries, not answer text

The evaluation SHALL score an answer by comparing the entry identifiers it cited against those
recorded for the question, reporting how many expected entries were cited and how many cited
entries were not expected. It SHALL NOT score by string comparison of the answer prose.

Of the expected entries an answer did not cite, the evaluation SHALL report separately those the
agent retrieved and passed over from those it never retrieved. The two are different failures — one
of selection, one of search — and a single "missed" count would hide which is happening.

#### Scenario: Answer cites the expected entries
- **WHEN** an answer cites every entry recorded for the question
- **THEN** it is scored as citing all expected entries

#### Scenario: Answer cites unexpected entries
- **WHEN** an answer cites entries not recorded for the question
- **THEN** those are reported separately rather than counted as errors, since the corpus may support the answer through entries the question set does not list

#### Scenario: An expected entry was retrieved and passed over
- **WHEN** an expected entry was returned by a retrieval during the question and the answer did not cite it
- **THEN** it is reported as passed over, apart from expected entries that were never retrieved

### Requirement: A cited value is checked against its entry

For every citation in an answer, the evaluation SHALL look for a quantity stated beside it and
compare that quantity with the cited entry's value or range as the corpus records it, and SHALL
compare the unit stated beside it with the entry's unit. Per citation it SHALL report one of: the
value matches the entry as written; the value matches only under a rescaling; the value does not
match; no quantity was found beside the citation. The unit comparison SHALL report compatible,
incompatible, or unknown, and SHALL NOT count unknown as either.

A match only under rescaling SHALL be listed for reading and SHALL NOT be counted as a match. A
genuine conversion and a thousandfold error look identical to this check, and the second is the
failure the project exists to prevent, so the cheap direction absorbs the doubt: a correct
conversion costs a line someone reads.

An entry identifier with no quantity beside it, or with the wrong one, is a right citation and a
useless answer; identifier scoring alone cannot see either.

#### Scenario: The value matches as written
- **WHEN** the quantity beside a citation equals the cited entry's value, or lies within its range, in the entry's unit
- **THEN** the citation is scored as a value match

#### Scenario: The value matches only under rescaling
- **WHEN** the quantity beside a citation equals the entry's value only after a power-of-ten rescaling
- **THEN** the citation is listed as matching under rescaling
- **AND** it is not counted as a match

#### Scenario: The value does not match
- **WHEN** the quantity beside a citation matches the entry's value or range under no rescaling
- **THEN** the citation is scored as a value mismatch and listed with both figures

#### Scenario: No quantity beside the citation
- **WHEN** no quantity is found beside a citation
- **THEN** the citation is reported as bare

#### Scenario: The unit is incompatible
- **WHEN** the unit beside a citation measures a different kind of thing from the entry's unit
- **THEN** the citation is scored as a unit mismatch

#### Scenario: The unit is unknown
- **WHEN** either unit cannot be classified
- **THEN** the citation's unit comparison is reported as unknown
- **AND** it counts as neither a match nor a mismatch

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

### Requirement: The agent's own grounding warnings are scored

The evaluation SHALL score, from what the agent reports about each question, a citation of an entry
not retrieved during the question, a citation of an identifier not in the corpus, and an answer
reached without any retrieval — including one whose prose claims a search was made — as grounding
failures, reported apart from citation-set, value and refusal scoring.

These are facts the agent already establishes about its own run, without judging the answer. A
refusal reached without searching is not a correct decline, and a cited entry the agent never saw
came from the model's memory; both would otherwise be scored as successes.

#### Scenario: An answer cites an entry it never retrieved
- **WHEN** an answer cites an entry that no retrieval during the question returned
- **THEN** it is scored as a grounding failure and listed

#### Scenario: A refusal without retrieval
- **WHEN** an unsupported question is declined and no retrieval was made
- **THEN** it is scored as an ungrounded refusal, apart from correctly declined

#### Scenario: The prose claims a search that did not happen
- **WHEN** an answer reached without retrieval describes having searched
- **THEN** that is counted separately from a plain ungrounded answer

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

Each recorded result SHALL carry the question as asked, the answer produced, the entries cited, the
entries retrieved, the entries expected, and the context shown to the agent, in a form that can be
read by evaluation tooling other than this project's own reporter.

Retrofitting this shape later would mean re-running the evaluation to regenerate every record, so
the cost of adopting an external tool would be paid in model spend rather than in code.

#### Scenario: A result is recorded
- **WHEN** a question's result is written
- **THEN** it carries the question, the answer, the cited, retrieved and expected entries, the context shown to the agent, and what produced it

#### Scenario: Results are read by another tool
- **WHEN** a results file is read by evaluation tooling that is not this project's reporter
- **THEN** each record supplies the question, the answer, the retrieved context, and the expected result without transformation

### Requirement: The context shown to the agent is recorded verbatim

Each recorded result SHALL carry the retrieval results the agent was shown while answering that
question, as the agent received them, and SHALL NOT substitute the corpus entries those results
refer to. A question that retrieved nothing SHALL be recorded with an empty context, distinguishable
from a result whose context was not recorded.

What the agent was shown and what the corpus holds are different things: a search shows one summary
line per entry and only a direct lookup shows an entry's body, so a judge given whole entries would
score groundedness against material the agent never had.

#### Scenario: A question retrieved entries
- **WHEN** a result is written for a question during which retrievals were made
- **THEN** the result carries each retrieval's result as the agent received it

#### Scenario: A question retrieved nothing
- **WHEN** a result is written for a question during which no retrieval was made
- **THEN** the result records that the context was empty
- **AND** that is distinguishable from a result whose context is absent

### Requirement: Every result records what produced it

Each recorded result SHALL name the model that produced the answer and every model setting that
shapes an answer — the reasoning effort where one is configured, and any sampling setting — together
with the identity of the instructions given to the model, the identity of the corpus asked (a digest
of its content and its entry count), the version of the code, and the time the question was asked.
Every report SHALL state the model or models its figures came from. A report covering results from
more than one model, more than one set of instructions, or more than one corpus SHALL break its
figures down rather than combine them.

Without this, a baseline taken on a cheap development model is silently compared against one taken on
a capable model, and a change of model reads as a change in quality. The same holds for a reworded
prompt and for a corpus that gained entries between two runs: each moves the figures, and a result
that does not say which corpus it was asked of cannot be compared with one asked of another. It also
separates the two explanations for a failed citation requirement — a defective harness, or a model
not strong enough to follow it — which are otherwise indistinguishable from the score alone.

#### Scenario: A result is recorded
- **WHEN** a question's result is written
- **THEN** it names the model and its settings, the instructions' identity, the corpus's identity, the code version, and the time

#### Scenario: A report covers one model
- **WHEN** every result in a report came from the same model
- **THEN** the report names that model alongside its figures

#### Scenario: A report covers several models
- **WHEN** results from more than one model are present
- **THEN** the figures are reported per model
- **AND** no figure combines results across models

#### Scenario: The corpus changed between runs
- **WHEN** results in a report were produced against corpora with different identities
- **THEN** the figures are reported per corpus
- **AND** the report says the corpus differed

### Requirement: Cost and effort are reported

Each evaluation run SHALL report the model cost it incurred and the number of tool calls made, so
that a change improving accuracy at several times the cost is visible as such.

#### Scenario: An evaluation run completes
- **WHEN** a run finishes
- **THEN** the report states the model cost and the total tool calls
- **AND** states them per question as well as in aggregate
