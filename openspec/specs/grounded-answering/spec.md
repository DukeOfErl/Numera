# grounded-answering Specification

## Purpose
Answers a natural-language question using only what was retrieved from the corpus, with every claim
attributable to a specific entry. In a project whose premise is verifiable provenance, a plausible
unsourced number is the worst output the system can produce — worse than admitting ignorance,
because it looks like the good case.

## Requirements

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
form SHALL be given to the model as an instruction, and SHALL be **delimited** — carrying a mark
where the identifier ends as well as where it begins. Parsing SHALL NOT infer an identifier from a
bare number.

Three reasons now. A reader comparing several answers should see citations look the same every time.
A bare six-digit number is indistinguishable from a six-digit quantity, so a parser without a marker
cannot tell a citation from a measurement. And a form that marks only its start forces the parser to
infer where the identifier ends — which requires rules about the identifier's own shape, each of
which is a place a corpus with differently shaped identifiers would break.

The instruction given to the model SHALL be produced from the same definition the parser uses, not
restated alongside it. A prompt asking for a form the parser does not read produces answers reported
as uncited, with nothing failing.

Parsing MAY additionally accept a form the system does not ask for, where readers are known to
introduce it. A reader familiar with the source's own notation writes it in their question; a
session's follow-up questions inherit the conversation, so from that point the model answers in it.
Rejecting it would report well-cited answers as unsupported, and a false negative here is worse than
the ambiguity that accepting it admits. Where a second form is accepted, identifiers SHALL be
ordered by where they appear in the text rather than grouped by which form wrote them.

A delimited group that holds no identifier SHALL be recorded rather than discarded silently. An
answer that tried to cite and failed is otherwise indistinguishable from one that never tried.

#### Scenario: An answer cites an entry
- **WHEN** an answer rests on an entry
- **THEN** the identifier appears in the stated form
- **AND** the same form is used for every identifier in that answer

#### Scenario: A quantity resembles an identifier
- **WHEN** an answer states a quantity whose digits could be read as an identifier
- **THEN** it is not parsed as a citation
- **AND** only delimited identifiers are counted

#### Scenario: The instruction and the parser cannot disagree
- **WHEN** the citation form changes
- **THEN** the instruction given to the model changes with it

#### Scenario: A reader introduces the source's own notation
- **WHEN** an answer cites an identifier in a notation the reader used rather than the stated form
- **THEN** the citation is still counted
- **AND** it is ordered among the others by where it appears

#### Scenario: A citation that cannot be read
- **WHEN** an answer contains a delimited group holding no identifier
- **THEN** it is not counted as a citation
- **AND** the occurrence is recorded

#### Scenario: An identifier that was never retrieved
- **WHEN** an answer cites an identifier that no tool call returned
- **THEN** this is detectable from the emitted events
- **AND** it is reported rather than accepted

### Requirement: Every answer is accompanied by the entries behind it

An answer SHALL be accompanied by the corpus entries the question retrieved, presented as a table
carrying at least the property, the organism, the value with its units, the identifier and the
reference -- on the web, a short form of the reference (first author and year) under the property,
with the full reference in the entry when it is opened. On the web the table SHALL wrap a long
property rather than cut it, and SHALL sit beside the answer, where the full entry is also opened. Entries an answer cited SHALL be shown before those it did not, and the boundary between
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
- **AND** each shows its property, organism, value with units, identifier and reference

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

The system SHALL answer from retrieved entries alone, and SHALL NOT present general knowledge as a
corpus-supported result.

WHERE nothing relevant is found, the answer SHALL report that it could not be found rather than that
the corpus does not hold it, and SHALL say briefly what was searched. The two are different claims
and only the weaker one is ever established: searching is a handful of wordings against a corpus that
words the same quantity many ways, so a failed search is evidence about the search. A retrieval miss
stated as an absence is a false negative delivered with more confidence than any part of the system
has earned -- and it has already happened, a question about ribosome density being refused as having
no volume entry while `Cell volume` sat in the corpus unsearched. Retrieval misses cannot be
eliminated; reporting them as absences can be.

#### Scenario: Nothing relevant is found
- **WHEN** searching and vocabulary discovery surface nothing relevant
- **THEN** the answer states that it could not find the quantity, not that the corpus lacks it
- **AND** names briefly what was searched
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

### Requirement: A refusal follows a search

The system SHALL NOT report that the corpus does not cover a question without having searched it,
and SHALL NOT describe retrieval that did not happen.

"Not in the corpus" and "not looked for" are different statements, and a reader cannot tell them
apart from the answer. A refusal reached without retrieval rests on the model's prior about what the
corpus contains, which is the thing this project exists not to rely on -- and its error is invisible,
because an entry that was never sought looks exactly like one that is absent.

Prose claiming a search that no tool call made SHALL be treated as a defect rather than a wording
choice. The number of tool calls is recorded on the ending event, so the claim is checkable against
the harness's own count without judging the answer's content.

#### Scenario: A question the corpus cannot answer
- **WHEN** the agent is asked something outside the corpus
- **THEN** at least one retrieval is attempted before any refusal is returned
- **AND** the refusal states that nothing was found, not that nothing exists

#### Scenario: An answer describes searches that were not made
- **WHEN** an answer claims to have searched and the question made no tool calls
- **THEN** this is reported as a defect in the same way an unsupported citation is

#### Scenario: Retrieval is impossible
- **WHEN** no retrieval can be attempted, because a limit was already reached
- **THEN** the ending says so as its reason
- **AND** the answer does not describe searching that did not occur

### Requirement: A cited entry from the store is shown with its trust tier as stars

Where the corpus is the harvest store, every citation in an answer and every row of the entries
shown with it SHALL carry the entry's trust tier as stars on one scale: five for a curated entry,
then four, three, two and one for the highest reviewer role that approved it — senior scientist,
scientist, student, AI — and zero where no one approved it. The tier SHALL be the one ADR-0990's
rule reads off the store's decisions.

The stars SHALL be drawn by the application from the store, never written by the model, and the
model SHALL NOT be asked to write them. A tier the model writes is a tier it can get wrong, and a
wrong star rating looks exactly like a right one. Where the model writes stars anyway, they SHALL
NOT be taken for the tier.

A disputed entry — one a reviewer objected to, whether or not another approved it — SHALL carry a
caution beside its stars, drawn so it stands out from the text (yellow on the page). What each
objecting reviewer said SHALL be shown where the reader opens the entry -- on the web, in the
entry beside the table; in the terminal, which cannot open one, listed under its table -- so a
reader who sees the caution can learn why. A reviewer's
words are shown to the reader only, never to the model. The stars say who approved it; the caution says that someone did not, and
neither is folded into the other.

Wherever a tier was set by a simulated review, the stars SHALL carry a mark saying so (`sim`, after
the stars: `#` was dropped because papers label their rings and samples "#1–#4"), and what the
mark means SHALL be stated with the entries the answer rests on. The demo's reviews are models standing in for people,
and a star a reader takes for a person's judgement is a claim the store does not make.

What the scale means SHALL be stated once for the page, where it stays in view beside the question
box, because it bears on practically every answer and table: which role each count stands for, what
the simulated mark and the caution mean and what zero means. It SHALL NOT be repeated under each
answer or each table. The caveat marks, which depend on the entries shown, keep their legend under
the table.

An entry from a corpus file carries no tier, and SHALL show no stars — not zero stars, which would
say that someone looked and no one approved.

#### Scenario: An answer cites a curated entry
- **WHEN** an answer cites a curated entry
- **THEN** five stars are shown beside the citation and in its row

#### Scenario: An entry approved by a student and a scientist, and objected to by another student
- **WHEN** an answer cites an entry a student and a scientist approved and another student objected to
- **THEN** three stars are shown, for the scientist
- **AND** a caution is shown beside them

#### Scenario: An entry no one approved
- **WHEN** an answer cites an entry that reviewers objected to and no one approved
- **THEN** zero stars are shown, with a caution

#### Scenario: A tier set by a simulated review
- **WHEN** the review that set an entry's tier was simulated
- **THEN** its stars carry the simulated mark
- **AND** what the mark means is stated once for the page, in view beside the question box

#### Scenario: A reader asks why an entry is disputed
- **WHEN** a reader opens a disputed entry
- **THEN** it shows what each objecting reviewer said, introduced by the reviewer's role and marked
  where the review was simulated
- **AND** its row in the table carries the stars and the caution only
- **AND** none of it is in anything the model receives

#### Scenario: The model writes stars
- **WHEN** the model's answer contains star characters beside a citation
- **THEN** the tier shown is still the one read from the store

#### Scenario: The corpus is a file
- **WHEN** the corpus is a corpus file
- **THEN** no stars, caution or simulated mark is shown on any citation or row

### Requirement: An entry's caveat marks have a column of their own

Where the entries behind an answer are shown as a table, the marks that qualify an entry — no
method recorded, cited but not retrieved, a hedged or fused range, an implausible span, no scalar
value, a value that could not be read with certainty, a calculated value — SHALL NOT be attached to
the property. In the terminal they SHALL be shown in a narrow column of their own, before every
other column, with that cell empty where no mark applies and the header MAY be empty. On the web,
where the value and its units share one cell, they SHALL follow the value, which is what they
qualify. The legend SHALL state what each mark shown means, as it does now.

Marks attached to the property make a reader read past symbols to reach the name, and scatter the
marks at varying offsets where a column lines them up. The marks that qualify a trust tier — a
dispute, a simulated review — are not caveat marks of the entry and SHALL stay with the stars.

#### Scenario: An entry with caveats
- **WHEN** an entry with no method recorded is shown in the table
- **THEN** its mark is in the terminal's first column, and after the value on the web
- **AND** its property cell holds the property alone

#### Scenario: An entry with none
- **WHEN** an entry to which no caveat applies is shown
- **THEN** no mark is shown with it

#### Scenario: A calculated value whose reading is uncertain
- **WHEN** a harvested entry is calculated and its value could not be read with certainty
- **THEN** both marks are shown with it
- **AND** the legend states what each means

### Requirement: An answer cites entries, never papers

The agent SHALL be instructed that an entry's identifier is the only citation an answer carries:
it SHALL NOT name a paper -- its authors, title, journal, year or DOI -- whether read from an
entry or recalled from its own knowledge. Each cited entry's reference is shown in the entries
table, by the application. A reference the model writes is unchecked: live answers over the store
(2026-10-16) added "(Kamasaki et al., 2007, JCB, doi:…)", whose authors and journal no entry
holds, and a citation in prose could name a paper other than the one the entry came from.
A prohibition alone leaves a model pressed by the reader nothing to say but a refusal or a
reference from memory, so the agent SHALL be told where the reference is, and to say so.

#### Scenario: The agent is given its instructions
- **WHEN** the agent is given its instructions
- **THEN** they say to cite by entry identifier only, and to name no paper, author, journal, year
  or DOI

#### Scenario: The reader asks which paper a value comes from
- **WHEN** the reader asks for a value's paper, its authors, journal or DOI
- **THEN** the agent's instructions tell it to say the reference is in the Reference column of the
  entries table and in the entry's full listing, rather than to refuse or to write it out

### Requirement: Cited entries are numbered through the session

On the web, every citation in an answer SHALL be drawn as one small pill carrying the entry's number
and, where the entry has a tier, its stars, the simulated mark and the caution. Entries SHALL be
numbered in the order the session first meets them -- the citations of each answer as they appear,
then that answer's other entries -- so a pill in an older answer still names one entry, and the
same entry keeps its number in every later answer. The identifier SHALL remain reachable from the
pill and SHALL be shown in the table and the opened entry. A citation of an identifier the corpus
does not hold SHALL get no number and SHALL be left as written. The stored answer, the trail, the
evaluation and the terminal keep the delimited form.

A long identifier in prose is read past; a number beside every cited value lets a reader match the
prose to the list at a glance, which is what the list is for.

#### Scenario: Two answers cite one entry
- **WHEN** a second answer in a session cites an entry the first answer cited
- **THEN** its pill carries the number the first answer gave it

#### Scenario: A citation the corpus does not hold
- **WHEN** an answer cites an identifier the corpus does not hold
- **THEN** no pill is drawn for it and the citation is shown as written

#### Scenario: The page is drawn again
- **WHEN** the page reruns and redraws the session's answers
- **THEN** every entry keeps its number

### Requirement: An entry is opened beside the answer

On the web, the full entry SHALL be opened in the evidence column, beside the answer, by choosing its
number under the table -- from one button per entry, or from a list where there are more than twelve
-- and not in the side panel. The opened entry SHALL show every field the corpus holds for it that
the table does not: the full reference with its links, the measurement method, and for a harvested
value the quote, the property in the paper's words, the conditions, what the paper does not state,
what a calculated value was calculated from, and what each objecting reviewer said. No entry SHALL be
open until the reader chooses one; choosing the open one again SHALL close it, the list SHALL offer
showing no entry, and sending a new question SHALL close every opened entry -- one record per turn,
open by default, filled the page as a conversation grew. The choice SHALL NOT be offered while the
agent is still answering, because a click re-runs the page and would cut the answer off.

#### Scenario: A reader opens an entry
- **WHEN** a reader chooses an entry's number under the table
- **THEN** that entry is shown in full in the evidence column
- **AND** before any is chosen, none is shown

#### Scenario: A new question is sent
- **WHEN** a reader sends a new question
- **THEN** every entry opened in an earlier turn is closed

#### Scenario: Many entries
- **WHEN** an answer has more than twelve entries
- **THEN** the choice is offered as a list rather than as buttons

#### Scenario: The agent is still answering
- **WHEN** a question is being answered
- **THEN** no entry can be chosen in any turn until the answer is complete
