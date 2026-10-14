# review-task

## Purpose

What a reviewer is shown for one claim, what they must decide, how the second text is chosen and
constrained so that clicking through is not an option, and what is recorded about the item and the
decision. The reviewer is the check that the mechanical checks cannot be.

## ADDED Requirements

### Requirement: One claim, one item, one screen

Each verified claim SHALL become exactly one review item, and a reviewer SHALL be shown one item at
a time, in two steps. The first step SHALL show: the property question; the paper's citation
(title, year, identifiers); and two texts from the paper, each with its section path and container,
in an order that carries no information about which is which. It SHALL NOT show the value, the
paper's own term for the property, or the conditions: each points at the text that is meant, and
choosing the text is the judgement the step asks for. The second step SHALL add: the value as the
paper states it, with its unit; the paper's own term for the property beside the question's; and a
condition block listing each condition and method field with its quote and its provenance state.

Each text SHALL be shown as the paper wrote it: the value under review SHALL NOT be highlighted or
otherwise distinguished within a text, so that nothing on the screen points at the number the
reviewer is asked to find, and bibliographic citation markers SHALL be kept as visible tokens rather
than stripped. A table cell SHALL be shown as its row and column headers with the cell; the table it
sits in SHALL also be shown once, whole and as the paper laid it out, beneath the two texts, with its
label, caption and footnotes, and with the cells of both texts marked alike where they lie in it.
Each text SHALL be at most a few sentences.

#### Scenario: An item is shown
- **WHEN** a reviewer opens the next item
- **THEN** the question, the citation and two located texts are on the screen, the value and the condition block are not, and nothing about the second text's kind is shown

#### Scenario: The entry is revealed
- **WHEN** a reviewer has chosen a text and written the value they read
- **THEN** the value, the paper's term and the condition block appear on the same screen as the texts, the reviewer's own choice and reading are repeated to them, and one line says how their reading stands to the stored value

#### Scenario: A cited sentence appears as a text
- **WHEN** one of the two texts contains a bibliographic citation marker in the paper
- **THEN** the marker is visible in the text as shown

#### Scenario: A text states the value
- **WHEN** one of the two texts contains the value under review
- **THEN** it is shown as the paper wrote it, with no emphasis on the value or on anything else

#### Scenario: A table cell is the supporting text
- **WHEN** the claim's quote is a table cell
- **THEN** the text shows the cell with its row and column headers, and the whole table appears once beneath the two texts with its caption, that cell marked and the other text's cell marked the same way if it is in the same table

### Requirement: The reviewer first chooses a text and reads its value, then gives a verdict

A reviewer SHALL be required, with the stored value withheld, to choose which of the two texts
states a value for the quantity under review -- the two shown side by side, the choice made on
the text itself and changeable until the step is saved -- and to write the value that text
states, as written.
That choice and reading SHALL be recorded before the stored value is shown. The reviewer SHALL then
record whether they approve or disapprove that this value, under the conditions shown, came from
this paper, and SHALL be able to add a free-text comment. Both steps are required before the next
item is offered. An item SHALL NOT be skipped silently: a reviewer who cannot decide SHALL
disapprove, and the comment is where they say why, or SHALL raise an issue, at either step, in
place of what remains, with its text.

The choice is made every time, whether or not the second text is a distractor, so that the presence
of a choice carries no information about the item. The value is written before the reveal so that
the reviewer's reading is a measurement of the entry the extractor's answer cannot have steered.
Raising an issue SHALL take a second confirming action and SHALL be cancellable before it.

#### Scenario: A reviewer completes an item
- **WHEN** a reviewer has chosen a text and written its value, and then, shown the stored entry, given a verdict
- **THEN** one decision is recorded with the choice, the value read, the verdict and the comment if any, and the next item is offered

#### Scenario: A reviewer continues without choosing a text or without a value
- **WHEN** a reviewer continues from the first step with no text chosen, or with no value written
- **THEN** nothing is revealed, nothing is recorded, and the reviewer is told which is required

#### Scenario: A reviewer gives no verdict
- **WHEN** a reviewer saves the second step with neither approval nor disapproval
- **THEN** the item is not completed, and the reviewer is told a verdict is required

#### Scenario: A reviewer leaves between the steps
- **WHEN** a reviewer has taken the first step on an item and opens the page again
- **THEN** that item is offered first, at its second step, with their choice and reading repeated

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
the value the reviewer read from it, written before the stored value was shown, and how that
reading stands to the stored value (the same number, the same number in another unit, a different
number, or no number), judged loosely at the reader's precision and across equivalent ways of
writing a number; the approval or
disapproval; the comment; the reviewer's account where one is signed in, and the absence of one
otherwise; the reviewer's role where one is known; the model, where a model and not a person
decided, and the model the provider says answered where that differs; and the time.

An issue raised in place of a decision SHALL be recorded as one: its text, no verdict, and the
choice and value read only if the issue was raised after them. An issue with no text SHALL be
refused. An item a reviewer raised an issue on is decided for that reviewer and SHALL NOT be
offered to them again.

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

#### Scenario: A decision by a signed-in reviewer carries their role
- **WHEN** a reviewer enrolled as a student, scientist or senior scientist completes an item or raises an issue
- **THEN** the row records that role, so the entry's tier can be read from it; a developer or administrator account records none

#### Scenario: An issue is raised before any text is chosen
- **WHEN** a reviewer raises an issue on an item at the first step and gives its text
- **THEN** the row holds the text, no choice and no verdict, and the item is not offered to that reviewer again

#### Scenario: An issue is raised after the reveal
- **WHEN** a reviewer raises an issue at the second step and gives its text
- **THEN** the row keeps the choice and the value read, holds the text and no verdict, and the item is not offered to that reviewer again

#### Scenario: An issue with no text
- **WHEN** an issue is raised with empty text
- **THEN** it is refused and nothing is recorded

### Requirement: Items are served so that every item is reviewed and none twice by the same reviewer

The next item offered to a reviewer SHALL be one they have not decided, and items SHALL be offered
in an order that does not group by paper, so a reviewer does not learn a paper's conditions from the
previous item. A reviewer SHALL be shown how many items remain for them. When none remain, they
SHALL be told so.

A human reviewer SHALL be able to narrow what they are offered to papers of one domain or one
topic, from those the loaded papers carry, and SHALL be able to set a paper aside, after which none
of its items is offered to them; a skip SHALL be recorded with the reviewer and the time, and SHALL
NOT count as a decision. None of these choices SHALL be available to a simulated reviewer, which
is offered its assigned items whatever any person chose or skipped.

#### Scenario: A reviewer returns
- **WHEN** a reviewer who has decided some items opens the page again
- **THEN** they are offered only items they have not decided

#### Scenario: Nothing remains
- **WHEN** a reviewer has decided every item
- **THEN** they are told there is nothing left to review

#### Scenario: A reviewer chooses a domain
- **WHEN** a human reviewer selects one domain
- **THEN** only items of papers in that domain are offered and counted for them

#### Scenario: A reviewer sets a paper aside
- **WHEN** a human reviewer skips the paper on screen
- **THEN** the skip is recorded, none of that paper's items is offered to them again, and the paper is still offered to other reviewers

#### Scenario: A model is not offered the choice
- **WHEN** a simulated reviewer runs after a person has skipped a paper
- **THEN** that paper's items are still among the ones it is given

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

A simulated reviewer SHALL be shown what a human reviewer is shown and nothing else, step by
step: the first step without the stored value, the second with it, the reviewer's own reading
recorded between the two. Never the second text's kind or type, and never another reviewer's
decision, choice or comment. Every role SHALL be given the same instruction, and the instruction
SHALL NOT name a role: a role is which model answers, not a manner of answering.

Every decision or issue a model writes SHALL record the model and the role, and SHALL be
distinguishable from a person's by the record alone. Any figure drawn from simulated decisions
SHALL be presented as simulated.

A simulated run SHALL be bounded in spend per decision and per run, and the call that would cross
either bound SHALL NOT be made. An item whose call fails SHALL get no decision and SHALL be offered
again on the next run. A refusal of the provider account, or the run's bound, SHALL stop the run.

#### Scenario: A model decides an item
- **WHEN** a simulated reviewer answers an item's first step with a text and a value, and its second with a verdict
- **THEN** one decision is recorded with its role, its model, the model that answered, the value read, and whether the chosen text was the supporting one

#### Scenario: A model is cut off between the steps
- **WHEN** a simulated reviewer's first step was recorded and its second step failed
- **THEN** the next run asks it only the second step for that item

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
### Requirement: An entry's trust tier is read off its decisions by one rule

Every reader that says how far an entry is trusted -- a dashboard, the ask agent, a page --
SHALL take it from one rule, and the rule SHALL return two things. The **tier** SHALL be
`curated` for a curated entry; otherwise the highest reviewer role among the decisions that
approved the entry with no issue beside them; otherwise none, nobody having approved it. The entry
SHALL be **disputed** when any decision disapproved it or raised an issue on it, and a dispute SHALL
NOT lower the tier: a reader is told both. An open row -- a choice awaiting its verdict -- SHALL
count as nothing. A tier set by a model standing in for a person SHALL be marked as simulated.

How the two are shown is each reader's: a dashboard MAY show a disputed entry as "issue raised" and
an unapproved one as "not yet reviewed"; the ask agent MAY show the tier as stars with a caution
when disputed. The rule itself SHALL be the same.

#### Scenario: The highest approving role sets the tier
- **WHEN** an entry was approved by the AI and by a scientist
- **THEN** its tier is scientist

#### Scenario: A dispute beside an approval
- **WHEN** a senior scientist approved an entry and a student disapproved it, or raised an issue
- **THEN** its tier is senior scientist and it is disputed

#### Scenario: Objected to and approved by no one
- **WHEN** an entry's only decision is a disapproval
- **THEN** its tier is none and it is disputed

#### Scenario: A simulated approval
- **WHEN** the highest approving decision was written by a model in the student's role
- **THEN** the tier is student and is marked simulated
