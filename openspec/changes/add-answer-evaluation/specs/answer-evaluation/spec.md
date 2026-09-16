## Purpose

Scores the agent's answers against a held-out set of questions whose supporting entries are known.
The agent is non-deterministic, so evaluation has to measure a distribution rather than check a
single run — this is the only way to tell an improvement from a lucky trajectory.

## ADDED Requirements

### Requirement: The question set is explicit and versioned with its answers

The evaluation SHALL read a question set in which each question records the entry identifiers that
should support its answer, and SHALL fail with an explanatory message when no question set is
supplied. Question sets SHALL NOT be generated at evaluation time by the system under test.

Each question SHALL record the property and the organism it asks about, in the corpus's own
vocabulary, so that whether the agent looked for them can be scored. Each question MAY carry tags
naming what it exercises — a comparison across entries, a conversion, an unsupported question, a
follow-up — and the report SHALL be able to give its figures per tag, so that a change which helps
one kind of question and harms another is visible as both.

The set SHALL include questions whose expected entries are complete — a scalar value, a classified
unit, a range that is not fused, a measurement method — and questions whose expected entries lack
each of those or carry a hedged range, and the report SHALL give its figures per entry shape. Most of
the corpus is incomplete in at least one of these ways, so a set drawn only from complete entries
measures the happy path and says nothing about the behaviour most questions will meet.

#### Scenario: Question set supplied
- **WHEN** the evaluation runs with a question set
- **THEN** each question is asked and scored against its recorded supporting entries

#### Scenario: No question set supplied
- **WHEN** the evaluation runs without one
- **THEN** it stops with a message explaining that a question set is required

#### Scenario: Figures per tag
- **WHEN** questions in the set carry tags
- **THEN** the report can give every figure for the questions carrying a given tag

#### Scenario: A question records what it asks
- **WHEN** a question is read from the set
- **THEN** it names the property and the organism asked

#### Scenario: Incomplete entries are in the set
- **WHEN** the set is validated
- **THEN** it holds questions whose expected entries have no scalar value, an unclassified unit, a fused range, no measurement method, and a hedged range
- **AND** the report gives its figures for each of those shapes apart from the complete ones

### Requirement: Scoring is based on entry identifiers, not answer text

The evaluation SHALL score an answer by comparing entry identifiers, never by string comparison of
the answer prose.

A question's **expected entries** SHALL be every entry in the corpus recording the asked property
for the asked organism, whatever spelling of that property it uses. `property` is free text, so one
quantity is recorded under many spellings, and a set naming one of them describes the search that
built it rather than the corpus. The set SHALL be built from the corpus vocabulary and SHALL NOT be
widened to what an agent cited: a set grown to what the system found is one the system passes by
construction.

An expected entry discharges its obligation by **reaching the entries table** — the table lists
every retrieved entry, the cited ones first — rather than by being cited in the prose. Requiring
prose citation of every expected entry would fail every good answer to a question the corpus
answers many times over. The evaluation SHALL therefore report, separately:

- whether every expected entry reached the table, and which did not;
- the rank of each expected entry within the table's ordering, because an entry ranked far down is
  one a reader never sees, and a search failure and a ranking failure need different fixes;
- how many expected entries the prose cited.

Where a driver truncates the table for display SHALL NOT be scored: the cut differs between drivers,
and scoring it would make one answer score differently depending on which driver asked.

A question MAY also record **admissible entries**: entries recording a *different* property that
nonetheless answers the question — the nucleoid where a bacterium was asked for a nucleus, cell
width where a rod was asked for a diameter. Citing one SHALL NOT be reported as unexpected, and
failing to cite one SHALL NOT be reported as a miss. A cited entry that is neither expected nor
admissible SHALL be reported as unexpected.

A question MAY record admissible entries and **no** expected entries. This is the false-premise
shape, and neither of the other two states describes it: nothing records the asked property, because
the thing asked about does not exist, yet the corpus holds material that answers what was meant.
Marking such a question unsupported would score the desired answer — cite the related entries and
say the premise does not hold — as a failure to decline. A question SHALL record at least one of the
two lists, or be marked unsupported; a question with neither would score as citing none of none,
which reads as a pass.

Of the expected entries an answer did not cite in prose, the evaluation SHALL report separately
those the agent retrieved and passed over from those it never retrieved. The two are different
failures — one of selection, one of search — and a single "missed" count would hide which is
happening. A passed-over entry SHALL NOT on its own be counted as an error: with the expected set
covering every spelling of a property, an answer citing some of them and leaving the rest to the
table is the intended shape.

#### Scenario: Every expected entry reaches the table
- **WHEN** every entry recorded for the question was retrieved during the question
- **THEN** the answer is scored as having brought every expected entry to the table, whether or not the prose cited each one

#### Scenario: An expected entry is never retrieved
- **WHEN** an entry recorded for the question was not retrieved during the question
- **THEN** it is reported as never retrieved, and the question fails the table check

#### Scenario: An expected entry reaches the table far down the ordering
- **WHEN** an expected entry was retrieved but is ranked below the entries the answer cited
- **THEN** its rank is reported, so a ranking failure is distinguishable from a search failure

#### Scenario: The display truncates the table
- **WHEN** a driver shows fewer rows than the table holds
- **THEN** the score is unchanged, because the cut belongs to the driver and not to the answer

#### Scenario: A question rests on admissible entries alone
- **WHEN** a question's premise is false and the corpus records only material answering what was meant
- **THEN** the question records those entries as admissible, records no expected entries, and is not marked unsupported

#### Scenario: Answer cites an admissible entry
- **WHEN** an answer cites an entry recorded for the question as admissible rather than expected
- **THEN** it is not reported as unexpected, and not counted towards the expected entries

#### Scenario: Answer cites entries recorded as neither expected nor admissible
- **WHEN** an answer cites entries the question set does not record
- **THEN** those are reported separately rather than counted as errors, since the corpus may support the answer through entries the question set does not list

#### Scenario: An expected entry was retrieved and passed over
- **WHEN** an expected entry was returned by a retrieval during the question and the answer did not cite it
- **THEN** it is reported as passed over, apart from expected entries that were never retrieved, and is not on its own counted as an error

### Requirement: The asked property and organism are recognised

The evaluation SHALL score, per question, whether any retrieval the agent made named the asked
organism — resolved the way the corpus's own search resolves an organism term, so an abbreviated
binomial counts — and whether any named the asked property, as a property or a keyword argument; and
SHALL report what fraction of the cited entries carry the asked organism and the asked property in
their own fields. The two are reported apart: what the agent asked for and what it settled on.

A right number for the wrong organism, or for a neighbouring property the search happened to return,
cites correctly and answers a different question. The retrieval arguments and the entries' fields
are both on record, so this needs no judge.

#### Scenario: The agent searched for what was asked
- **WHEN** a retrieval during the question names the asked organism and one names the asked property
- **THEN** the question is scored as having searched for both

#### Scenario: The agent never searched for the asked organism
- **WHEN** no retrieval during the question names the asked organism
- **THEN** the question is scored as not having searched for it, and listed with the terms it did search

#### Scenario: Cited entries belong to another organism
- **WHEN** a cited entry's organism field is not the asked organism
- **THEN** it is counted against the fraction of cited entries carrying the asked organism, and listed

### Requirement: A cited entry at odds with its peers is flagged

The evaluation SHALL compare each cited entry's recorded value against its **peers** — the entries
the question records as expected, sharing the cited entry's organism and its unit — and SHALL flag a
citation whose entry is a distant outlier among them. The flag SHALL name the entry, its value, and
the interval the peers occupy, and SHALL NOT be counted as an error.

**Peers are drawn from the question's expected entries, not from a property string.** `property` is
free text, so one quantity is recorded under many spellings — `Nuclear volume`, `Volume of nucleus`,
`Volume of nuclei during S phase` — and a pool keyed on wording is a pool keyed on coincidence. The
expected list is that vocabulary resolved against the corpus by hand and reviewed, so the comparison
reuses it rather than resolving a second time.

**Peers SHALL share the cited entry's unit**, and sameness of unit means the same recorded unit,
not merely the same dimension. A pool matched on dimension alone can place a volume in litres beside
one in cubic micrometres, which spans fifteen orders of magnitude and makes the interval meaningless
rather than wide.

This asks only which entries were cited, what the question expected, and what the corpus records, so
it needs no reading of the answer's prose. An answer can cite an entry that exists, attribute its
number correctly, and still lead with the one figure in the corpus that disagrees with every other
measurement of the same quantity. Every check that compares an answer against its own citations
passes such an answer, because nothing about it is internally wrong.

An outlier is a fact about the corpus rather than about the answer, so it is reported for reading
rather than scored against the answer: the entry may be measuring something its neighbours do not.

#### Scenario: A cited entry is an outlier
- **WHEN** a cited entry's value is a distant outlier among the question's expected entries sharing its organism and unit
- **THEN** the citation is flagged with that entry's value and the interval those peers occupy

#### Scenario: Every cited entry sits with its peers
- **WHEN** no cited entry's value is an outlier among its peers
- **THEN** no outlier is reported for the answer

#### Scenario: A citation the question did not expect
- **WHEN** an answer cites an entry the question does not record as expected
- **THEN** it is still compared against the question's expected entries that share its organism and unit, since it is judged against what the question is about rather than against its own neighbours

#### Scenario: Peers recorded in a different unit
- **WHEN** entries share the organism but record their values in a different unit
- **THEN** they are not peers, and the comparison is not made across them

#### Scenario: Too few peers to judge
- **WHEN** fewer entries share the cited entry's organism and unit than the comparison needs
- **THEN** no outlier is reported for it
- **AND** the report states that the comparison could not be made

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
