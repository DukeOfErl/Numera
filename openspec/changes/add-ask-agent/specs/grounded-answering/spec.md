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

### Requirement: Citations use one stated format

Entry identifiers SHALL be written in a single stated form wherever they appear in an answer. The
form SHALL be given to the model as an instruction, and parsing SHALL require the identifier to carry
its marker rather than inferring one from a bare number.

Two reasons, and both matter. A reader comparing several answers should see citations look the same
every time. And a bare six-digit number is indistinguishable from a six-digit quantity, so a parser
without a marker cannot tell a citation from a measurement — an ambiguity that grows as the corpus
does.

#### Scenario: An answer cites an entry
- **WHEN** an answer rests on an entry
- **THEN** the identifier appears in the stated form
- **AND** the same form is used for every identifier in that answer

#### Scenario: A quantity resembles an identifier
- **WHEN** an answer states a quantity whose digits could be read as an identifier
- **THEN** it is not parsed as a citation
- **AND** only identifiers carrying the marker are counted

#### Scenario: An identifier that was never retrieved
- **WHEN** an answer cites an identifier that no tool call returned
- **THEN** this is detectable from the emitted events
- **AND** it is reported rather than accepted

### Requirement: Every answer is accompanied by the entries behind it

An answer SHALL be accompanied by the corpus entries the question retrieved, presented as a table
carrying at least the property, the organism, the value, the units, the identifier and the
reference. Entries an answer cited SHALL be shown before those it did not, and the boundary between
the two SHALL be visible. Where more entries were retrieved than are shown, the presentation SHALL
say so.

An entry whose measurement method the corpus does not record SHALL be marked as such. A textbook
page and a measurement over a thousand cells otherwise read identically in a table, and which of the
two a number came from is exactly what a reader is there to judge. Only the absence is asserted:
nothing grades an entry that does record a method.

Entries an answer did not cite SHALL be ordered by relevance to the question rather than by the
order they were retrieved in. For a single search, retrieval order is the corpus's own identifier
order, which carries no relevance at all -- it is what put a 490 um chromosome among the top five
entries shown for a question about a 1 um cell. The ordering in this change is string overlap
between the question, the cited entries' properties and each candidate's property: enough to sink
entries that are plainly about another object, and not enough to tell a flagellum from a cell. A
better one is deferred, not forgotten.

Prose alone cannot be checked. A reader given the entries beside the answer can see what the model
was working from, and the reference is what lets them go to the paper rather than trusting either the
model or the corpus. This is the same reasoning as citing identifiers, carried through to what a
person actually reads.

An entry an answer cited that no tool call returned SHALL be marked as such where it is shown. The
entry exists, so nothing about the row looks wrong, which is why it needs the mark: unmarked it sits
among the cited entries as though the answer rested on it legitimately.

The reference SHALL NOT be included in what is sent to the model. It is presentation, not evidence
the model reasons over, and references are long enough that carrying them into every search result
would more than double what a search costs.

A value SHALL be shown as the corpus holds it or visibly abbreviated, never silently altered. Where
a cell does not fit, the truncation SHALL be marked. Splitting a number across two lines is
forbidden: `6800.0-72000.0` broken over a line read as `6800.0-72000.` above a lone `0` — a value the
corpus does not hold, displayed with nothing to say it had been changed.

#### Scenario: A question is answered
- **WHEN** an answer is produced
- **THEN** the entries retrieved for it are presented alongside it
- **AND** each shows its property, organism, value, units, identifier and reference

#### Scenario: A value too wide for its column
- **WHEN** a value does not fit the space the presentation gives it
- **THEN** it is abbreviated with a visible mark rather than broken across lines
- **AND** no number the corpus does not hold is displayed

#### Scenario: More entries than are shown
- **WHEN** more entries were retrieved than the presentation shows
- **THEN** how many were retrieved is stated
- **AND** how many the corpus matched is stated, which may exceed what was retrieved

#### Scenario: The entries an answer rests on are distinguishable
- **WHEN** both cited and uncited entries are shown
- **THEN** the boundary between them is visible
- **AND** the uncited entries are still shown, because what the corpus held and the answer passed
  over is part of the evidence

#### Scenario: An entry records no measurement method
- **WHEN** an entry whose measurement method the corpus does not record is shown
- **THEN** it is marked as such
- **AND** what the marking means is stated where it is shown

#### Scenario: An entry was cited but never retrieved
- **WHEN** an answer cites an entry the corpus holds but no tool call returned
- **THEN** the citation is reported as unsupported
- **AND** the entry is shown marked as cited without being retrieved
- **AND** this holds whether or not anything else was retrieved

#### Scenario: The presentation is not the model's work
- **WHEN** the entries are presented
- **THEN** every field shown is read from the corpus
- **AND** an identifier the corpus does not hold produces no row

#### Scenario: Several searches contributed
- **WHEN** more than one search ran
- **THEN** the number of searches is stated alongside the matched total
- **AND** the total is not presented as a count of distinct entries

#### Scenario: A question ends without an answer
- **WHEN** a question ends on a limit having retrieved entries
- **THEN** those entries are still presented
- **AND** the reader can see what had been found before it stopped

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

Compatibility SHALL be three-valued: compatible, incompatible, or unknown. A unit the system does
not recognise SHALL NOT be treated as compatible with anything, and SHALL NOT be treated as
dimensionless either. Classification will always be partial — the reference corpus carries over two
thousand distinct unit strings, whose forty-five commonest cover under two thirds of it — so
"unknown" is the normal case and must be a first-class answer rather than a gap that defaults to a
guess. Where case alone distinguishes two quantities, as in millimolar and millimetres, it SHALL be
honoured; where a symbol is genuinely ambiguous across dimensions, the answer SHALL be unknown.

Where a set of entries offered to the model spans more than one dimension, the system SHALL say so
in the tool result carrying those entries — at the point the model decides what to say, not only in
a rule stated earlier — naming how many kinds of quantity are present and that values of different
kinds are not alternative estimates of one quantity.

#### Scenario: Two entries report related quantities in incompatible units
- **WHEN** two retrieved entries carry units of different dimensions
- **THEN** they are not presented as a range or a disagreement
- **AND** each is reported separately with its own units

#### Scenario: An unrecognised unit
- **WHEN** an entry carries units the system does not recognise
- **THEN** its compatibility with any other unit is reported as unknown
- **AND** it is not presented as comparable to anything on the strength of that

#### Scenario: A search returns entries of more than one kind
- **WHEN** the entries returned for a search span more than one dimension
- **THEN** the result says how many kinds of quantity they measure and names them
- **AND** states that values of different kinds are not alternative estimates of one quantity

#### Scenario: An answer cites entries of more than one kind
- **WHEN** the entries an answer cites span more than one dimension
- **THEN** the presentation states how many kinds of quantity they measure and names them
- **AND** this covers every cited entry, not only the ones the presentation had room to show
- **AND** nothing is stated where the cited entries measure one kind, so the statement stays
  readable as a fact rather than as noise

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

The presentation SHALL make the recorded conditions visible for the entries an answer cites, so a
reader can check the prose's account of what distinguishes them rather than taking it on trust.
Marking only the *absence* of a method is not enough: a textbook page and a count over a thousand
cells appear identical in a table, and which of the two produced a number is exactly what a reader is
there to judge. Where a recorded condition is too long to show whole, it SHALL be abbreviated with
the abbreviation marked, never silently cut.

#### Scenario: Cited entries record how they were measured
- **WHEN** an answer cites two or more entries whose measurement method the corpus records
- **THEN** the presentation shows each of those entries' recorded method beside its identifier
- **AND** an entry recording no method is left out of that listing, its absence already marked

#### Scenario: A single cited entry
- **WHEN** an answer cites only one entry
- **THEN** no distinguishing conditions are listed, there being nothing to distinguish it from

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

An answer produced with no calls left stopped searching because it ran out of room, not because it
was satisfied, and the two are otherwise indistinguishable. The report SHALL state the calls used
against the bound, and SHALL do so only where the bound was actually reached: a figure printed
beside every answer is noise where it means nothing. Whether the bound was reached SHALL be
determined by the count that enforces it, so a call retried after a provider failure counts once.

#### Scenario: Question is answered within the bound
- **WHEN** retrieval completes before the bound is reached
- **THEN** the answer is returned with no truncation notice
- **AND** nothing is said about the bound

#### Scenario: An answer is produced with no calls left
- **WHEN** an answer is produced on the last call the bound allows
- **THEN** the calls used and the bound are both reported
- **AND** the answer is not marked incomplete, the bound being a fact about how it was reached

#### Scenario: A question never reaches the model
- **WHEN** a question ends before any model call
- **THEN** no bound is reported, since none was applied

#### Scenario: Bound is reached first
- **WHEN** the tool-call bound is reached before retrieval is complete
- **THEN** the answer states that it may be incomplete
- **AND** what had been established so far is still presented with citations

#### Scenario: The spend ceiling is reached first
- **WHEN** answering is halted by the spend ceiling (see `spend-control`)
- **THEN** the answer states that it may be incomplete
- **AND** what had been established so far is still presented with citations
