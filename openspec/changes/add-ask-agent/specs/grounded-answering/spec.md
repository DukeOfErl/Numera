## Purpose

Answers a natural-language question using only what was retrieved from the corpus, with every claim
attributable to a specific entry. In a project whose premise is verifiable provenance, a plausible
unsourced number is the worst output the system can produce — worse than admitting ignorance,
because it looks like the good case.

## ADDED Requirements

### Requirement: Every quantitative claim cites its entries

Every quantity stated in an answer SHALL carry the identifier of the entry it came from. The system
SHALL NOT state a quantity that cannot be attributed to a retrieved entry.

#### Scenario: Answer states a value
- **WHEN** an answer states a quantity
- **THEN** the identifier of the entry supplying it is presented with it

#### Scenario: A candidate claim cannot be attributed
- **WHEN** a quantity under consideration does not correspond to any retrieved entry
- **THEN** it is omitted from the answer

### Requirement: Answers come only from the corpus

The system SHALL answer from retrieved entries alone. WHERE the corpus does not cover a question,
it SHALL say so plainly rather than answering from the model's own knowledge, and SHALL NOT present
general knowledge as a corpus-supported result.

#### Scenario: Corpus does not cover the question
- **WHEN** searching and vocabulary discovery establish that the corpus holds nothing relevant
- **THEN** the answer states that the corpus does not cover it
- **AND** states no quantity

#### Scenario: Corpus covers the question partially
- **WHEN** retrieved entries answer part of the question only
- **THEN** the answer covers the supported part with citations
- **AND** states plainly which part is unsupported rather than completing it from general knowledge

### Requirement: Values are compared only when dimensionally compatible

Before presenting two entries as differing estimates of the same quantity, the system SHALL
establish that their units are dimensionally compatible. Values in incompatible units SHALL NOT be
presented as a range, a spread, or a disagreement.

This is not a hypothetical guard. In the reference corpus, `Non-yolk protein` in *Xenopus* appears
as `25 µg` in one entry and `5 × 10¹⁴ proteins` in another — a mass and a count. Presenting those as
"estimates ranging from 25 to 5 × 10¹⁴" would be meaningless, and naive numeric comparison across
entries produces exactly that.

#### Scenario: Two entries report the same quantity in compatible units
- **WHEN** two retrieved entries describe the same quantity with dimensionally compatible units
- **THEN** they may be presented together as differing estimates

#### Scenario: Two entries report related quantities in incompatible units
- **WHEN** two retrieved entries carry units of different dimensions
- **THEN** they are not presented as a range or a disagreement
- **AND** each is reported separately with its own units

### Requirement: Disagreement is reported with its conditions

WHERE retrieved entries give dimensionally compatible but differing values for the same quantity,
the answer SHALL present the differing values rather than selecting one silently, and SHALL report
the conditions that distinguish them where the entries record any.

Exact matching on property and organism strings finds only a small fraction of the corpus's real
disagreements, because the same quantity is worded differently across entries. Recognising that two
entries describe the same quantity is a judgment the agent makes, not a lookup.

#### Scenario: Entries disagree on a value
- **WHEN** two or more retrieved entries give differing compatible values for the same quantity
- **THEN** the answer presents each value with its citation
- **AND** presents the organism, method, or conditions that distinguish them where recorded

#### Scenario: One value is selected over another
- **WHEN** the answer presents a single value while other retrieved entries disagree
- **THEN** the answer states that other entries differ and why this one was preferred

### Requirement: Computed values are shown with their inputs

WHERE an answer presents a number that appears in no entry — a conversion, a ratio, an average — it
SHALL identify the number as computed and cite the entries supplying every input.

#### Scenario: Answer performs a computation
- **WHEN** an answer states a value derived from entry values rather than taken from an entry
- **THEN** it is marked as computed
- **AND** the entries supplying each input are cited

#### Scenario: Computation would need an unretrieved input
- **WHEN** a computation would require a quantity not present in any retrieved entry
- **THEN** the computation is not presented

### Requirement: Retrieval effort is bounded and reported

The system SHALL bound the number of tool calls made in answering a single question, and SHALL
report when an answer was produced against that bound rather than because retrieval was complete.

#### Scenario: Question is answered within the bound
- **WHEN** retrieval completes before the bound is reached
- **THEN** the answer is returned with no truncation notice

#### Scenario: Bound is reached first
- **WHEN** the tool-call bound is reached before retrieval is complete
- **THEN** the answer states that it may be incomplete
- **AND** what had been established so far is still presented with citations

#### Scenario: The spend ceiling is reached first
- **WHEN** answering is halted by the spend ceiling (see `spend-control`)
- **THEN** the answer states that it may be incomplete
- **AND** what had been established so far is still presented with citations
