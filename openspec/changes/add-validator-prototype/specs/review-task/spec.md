# review-task

## Purpose

What a reviewer is shown for one claim, what they must decide, how the second text is chosen and
constrained so that clicking through is not an option, and what is recorded about the item and the
decision. The reviewer is the check that the mechanical checks cannot be.

## ADDED Requirements

### Requirement: One claim, one item, one screen

Each verified claim SHALL become exactly one review item, and a reviewer SHALL be shown one item at
a time. An item SHALL show: the property question; the value as the paper states it, with its unit,
and the paper's own term for the property beside the question's; the paper's citation (title, year,
identifiers); a condition block listing each condition and method field with its quote and its
provenance state; and two texts from the paper, each with its section path and container, in an
order that carries no information about which is which.

Each text SHALL be shown as the paper wrote it: the value under review SHALL NOT be highlighted or
otherwise distinguished within a text, so that nothing on the screen points at the number the
reviewer is asked to find, and bibliographic citation markers SHALL be kept as visible tokens rather
than stripped. A table cell SHALL be shown as its row and column headers with the cell; the table it
sits in SHALL also be shown once, whole and as the paper laid it out, beneath the two texts, with its
label, caption and footnotes, and with the cells of both texts marked alike where they lie in it.
Each text SHALL be at most a few sentences.

#### Scenario: An item is shown
- **WHEN** a reviewer opens the next item
- **THEN** the question, the value, the citation, the condition block and two located texts are all on one screen, and nothing about the second text's kind is shown

#### Scenario: A cited sentence appears as a text
- **WHEN** one of the two texts contains a bibliographic citation marker in the paper
- **THEN** the marker is visible in the text as shown

#### Scenario: A text states the value
- **WHEN** one of the two texts contains the value under review
- **THEN** it is shown as the paper wrote it, with no emphasis on the value or on anything else

#### Scenario: A table cell is the supporting text
- **WHEN** the claim's quote is a table cell
- **THEN** the text shows the cell with its row and column headers, and the whole table appears once beneath the two texts with its caption, that cell marked and the other text's cell marked the same way if it is in the same table

### Requirement: The reviewer always chooses between two texts, and separately gives a verdict

A reviewer SHALL be required to choose which of the two texts better fits the value under review,
and SHALL separately record whether they approve or disapprove that this value, under the conditions
shown, came from this paper. Both are required before the next item is offered. The reviewer SHALL
be able to add a free-text comment. An item SHALL NOT be skipped silently: a reviewer who cannot
decide SHALL disapprove, and the comment is where they say why, or, where the reviewer is offered
it, SHALL raise an issue in place of both the choice and the verdict, with its text.

The choice is made every time, whether or not the second text is a distractor, so that the presence
of a choice carries no information about the item.

#### Scenario: A reviewer completes an item
- **WHEN** a reviewer has chosen a text and given a verdict
- **THEN** both are recorded at once, with the comment if any, and the next item is offered

#### Scenario: A reviewer gives a verdict without choosing a text
- **WHEN** a reviewer records approval or disapproval but has not chosen a text
- **THEN** the item is not completed, and the reviewer is told a choice is required

### Requirement: The second text is a distractor or a second occurrence, and its kind is recorded

For each item the second text SHALL be either a **distractor** — a passage from the same paper that
does not support the value — or a **second occurrence** — another passage from the same paper that
does legitimately state the same value for the same conditions. Which kind it is, and for a
distractor which type, SHALL be recorded with the item and SHALL NOT be shown to the reviewer.

A distractor SHALL be one of: a value for the same property under an adjacent condition; a value
for the property in a different organism or system, cited from other work; a different quantity
sharing the value's unit and subject; the same number used as a parameter or assumption rather than
measured; or the other half of a derivation sentence. A distractor SHALL differ from the supporting
text in a dimension named in the question or visible in the two texts as shown.

A distractor SHALL NOT be a value other work reports for the same property in the same organism:
that is a second source's answer to the question, not a text that fails to support the value. The
selector SHALL be instructed so; the prototype does not enforce it mechanically.

A distractor SHALL NOT contain the value under review, its rounding, or its unit-converted form,
and SHALL NOT be a passage that supports the value for the same conditions by another method. This
exclusion SHALL be enforced mechanically on the distractor's text before the item is created; a
candidate that fails it SHALL be rejected and another chosen. An item for which no admissible second
text exists SHALL NOT be created, and the claim SHALL be recorded as having no reviewable item with
that reason.

#### Scenario: A distractor is chosen from an adjacent table row
- **WHEN** the paper's table states the property for several conditions
- **THEN** a row for a different condition may be the distractor, and the item records kind distractor, type adjacent-condition

#### Scenario: A candidate distractor restates the value
- **WHEN** a candidate second text contains the value under review at any precision
- **THEN** it is rejected before the item is created

#### Scenario: A second legitimate occurrence
- **WHEN** the paper states the same value for the same conditions in two places
- **THEN** the second place may be the second text, and the item records kind second-occurrence

#### Scenario: No admissible second text
- **WHEN** no passage in the paper satisfies the distractor rules and there is no second occurrence
- **THEN** no item is created for the claim, and the claim is recorded as not reviewable with that reason

### Requirement: What is recorded about an item and a decision

For every item, the record SHALL hold: the property question; the value, unit and kind; the paper's
identifiers, title, year and licence; the supporting text with its location; the second text with
its location, kind and type; the tables the texts sit in, as shown; every condition and method field
with its quote and provenance state; and the fingerprint of what produced the claim (model,
instruction fingerprint, article, run). For
every decision, the record SHALL hold: which text was chosen; whether it was the supporting text;
the approval or disapproval; the comment; the reviewer's account where one is signed in, and the
absence of one otherwise; the reviewer's role where one is known; the model, where a model and not
a person decided; and the time.

An issue raised in place of a decision SHALL be recorded as one: its text, and neither a choice nor
a verdict. An issue with no text SHALL be refused. An item a reviewer raised an issue on is decided
for that reviewer and SHALL NOT be offered to them again.

A decision SHALL be written at the moment it is given, and the write SHALL **fail closed**: a
decision that could not be written SHALL be reported to the reviewer as not saved, and the item
SHALL NOT be marked done. A lost decision is the loss of the one thing this task exists to collect,
which is the opposite of the trail's case, where a lost row costs one row.

#### Scenario: A decision is saved
- **WHEN** a reviewer completes an item and the store accepts the write
- **THEN** the decision row holds the choice, whether it was the supporting text, the verdict, the comment, the reviewer and the time

#### Scenario: The store is unreachable
- **WHEN** a reviewer completes an item and the write fails
- **THEN** the reviewer is told the decision was not saved, and the item remains open

#### Scenario: A decision without sign-in
- **WHEN** a deployment has no identity configured and a reviewer completes an item
- **THEN** the decision is recorded with no account, and nothing else about it differs

#### Scenario: An issue is raised
- **WHEN** a reviewer raises an issue on an item and gives its text
- **THEN** the row holds the text, no choice and no verdict, and the item is not offered to that reviewer again

#### Scenario: An issue with no text
- **WHEN** an issue is raised with empty text
- **THEN** it is refused and nothing is recorded

### Requirement: Items are served so that every item is reviewed and none twice by the same reviewer

The next item offered to a reviewer SHALL be one they have not decided, and items SHALL be offered
in an order that does not group by paper, so a reviewer does not learn a paper's conditions from the
previous item. A reviewer SHALL be shown how many items remain for them. When none remain, they
SHALL be told so.

#### Scenario: A reviewer returns
- **WHEN** a reviewer who has decided some items opens the page again
- **THEN** they are offered only items they have not decided

#### Scenario: Nothing remains
- **WHEN** a reviewer has decided every item
- **THEN** they are told there is nothing left to review

### Requirement: The model is never shown a decision

No decision, choice or comment SHALL be passed to the extraction model or to the process that
chooses second texts. Decisions are the measurement of the extractor and cannot also be its input.

#### Scenario: A later run
- **WHEN** extraction or second-text selection runs after decisions exist
- **THEN** the instruction and inputs sent to the model contain no decision, choice or comment

### Requirement: A review may be simulated by models, and every simulated decision says so

Models MAY stand in for reviewers. Each simulated reviewer SHALL have a role, a model and a share
of the items, and SHALL decide only the items assigned to its role that it has not already decided.
Which items a role is assigned SHALL be fixed for the role and the item, the same on every run, and
drawn independently for each role, so that an item may be decided by several roles, by one, or by
none.

A simulated reviewer SHALL be shown what a human reviewer is shown and nothing else: never the
second text's kind or type, and never another reviewer's decision, choice or comment. Every role
SHALL be given the same instruction, and the instruction SHALL NOT name a role: a role is which
model answers, not a manner of answering.

Every decision or issue a model writes SHALL record the model and the role, and SHALL be
distinguishable from a person's by the record alone. Any figure drawn from simulated decisions
SHALL be presented as simulated.

A simulated run SHALL be bounded in spend per decision and per run, and the call that would cross
either bound SHALL NOT be made. An item whose call fails SHALL get no decision and SHALL be offered
again on the next run. A refusal of the provider account, or the run's bound, SHALL stop the run.

#### Scenario: A model decides an item
- **WHEN** a simulated reviewer answers an item with a text and a verdict
- **THEN** the decision is recorded with its role and its model, and whether the chosen text was the supporting one

#### Scenario: The screen does not depend on the second text's kind
- **WHEN** two items differ only in the kind and type of their second text
- **THEN** a simulated reviewer is shown the same thing for both

#### Scenario: Two roles review overlapping subsets
- **WHEN** two roles each review a share of the items
- **THEN** each reviews a subset fixed by its role, the two subsets differ, and some items are in both

#### Scenario: A run is repeated
- **WHEN** a simulated run is started again after decisions exist
- **THEN** no item a simulated reviewer has decided is asked about again

#### Scenario: The run's bound is reached
- **WHEN** the next call's projected cost would cross the run's bound
- **THEN** the call is not made, the run stops, and it says why

#### Scenario: A call fails
- **WHEN** the model's answer to one item cannot be read
- **THEN** no decision is recorded for it, the cost reported for the call is still counted, and the next item is reviewed
