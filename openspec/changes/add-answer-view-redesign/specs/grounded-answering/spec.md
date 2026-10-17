## ADDED Requirements

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
what a calculated value was calculated from, and what each objecting reviewer said. The choice SHALL
NOT be offered while the agent is still answering, because a click re-runs the page and would cut
the answer off.

#### Scenario: A reader opens an entry
- **WHEN** a reader chooses an entry's number under the table
- **THEN** that entry is shown in full in the evidence column

#### Scenario: Many entries
- **WHEN** an answer has more than twelve entries
- **THEN** the choice is offered as a list rather than as buttons

#### Scenario: The agent is still answering
- **WHEN** a question is being answered
- **THEN** no entry can be chosen in any turn until the answer is complete

## MODIFIED Requirements

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

What the scale means SHALL be stated once, with the entries table that accompanies the answer:
which role each count stands for, what the caution means and what zero means. It SHALL NOT be
repeated under the answer's prose, where it would be read before the evidence it explains and
again beside it.

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
- **AND** what the mark means is stated once, with the entries table

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
