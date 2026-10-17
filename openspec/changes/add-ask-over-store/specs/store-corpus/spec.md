## Purpose

Lets the agent answer from the harvest store — curated BioNumbers entries and numbers harvested from
papers — reading it as a corpus without writing to it, and carrying into each entry what a reader
needs to judge a harvested number.

## ADDED Requirements

### Requirement: The store is a corpus the agent can be pointed at, and is only read

The system SHALL accept the harvest store as the agent's corpus, as an alternative to a corpus file.
Which one is used SHALL be a matter of configuration; a corpus file SHALL keep loading and answering
exactly as before. The store SHALL be opened for reading only: nothing the agent or a driver does
SHALL create, modify or delete a row in it.

The store is the database of record for the review, written by another process while the agent
runs. A reader that could write would be a second writer nobody planned for, and the one table
everything else is checked against would stop being the record.

#### Scenario: The agent is pointed at the store
- **WHEN** the configured corpus is the harvest store
- **THEN** questions are answered from the store's entries
- **AND** after any number of questions no row in the store has changed

#### Scenario: The agent is pointed at a corpus file
- **WHEN** the configured corpus is a corpus file
- **THEN** it loads and answers as it did before this change
- **AND** no entry shows a trust tier

#### Scenario: The store cannot be opened
- **WHEN** the configured store is missing or unreadable
- **THEN** the run stops with a message naming what was configured
- **AND** no other corpus is substituted

### Requirement: The store's entries are its curated entries and its harvested values

The corpus read from the store SHALL hold every curated entry and every harvested value, from every
domain the store holds. A harvested entry SHALL be one extracted value — not a paper — so that a
question about a property finds the value rather than the paper it came from.

A curated entry SHALL keep its BioNumbers identifier. A harvested entry SHALL carry two
identifiers, with different jobs:

- **A label the model writes**: the paper's PMCID and the value's number within its extraction
  (`PMC2652108-1`), cited in the same delimited form as every other entry (`[[PMC2652108-1]]`). A
  label SHALL NOT name the extraction run or the model that produced the value.
- **The store's own identifier for the value**, which never changes and names one value forever.
  Everything saved about an answer — the trail and the question-and-answer records — SHALL hold this identifier for every harvested entry it cites, beside the label. A label SHALL NOT
  be the key anything is saved under.

A label is short because a model copies short identifiers reliably and long ones not; it is safe
only because it is resolved at once, against the store as loaded, and never saved alone. A paper
extracted again reuses its value numbers, so a label saved alone could later name a different
value.

Where one paper has been extracted more than once, each extraction's values SHALL be separate
entries — never merged, never silently dropped — and SHALL receive distinct labels: the earliest
extraction added to the store keeps `PMC2652108-1`, and each later one is told apart by a suffix
in the order the extractions were added (`PMC2652108-1.2`). An extraction added later never takes
an existing label, so a label keeps naming the same value while the store is only added to.

A label is nonetheless valid only within the load it was given in: a store rebuilt by adding its
extractions in another order would relabel them, so a label shown in an earlier answer could name a
different value after such a rebuild. Nothing saved SHALL ever be resolved again by its label; a saved answer is resolved
by the store's identifier it holds, and the label beside it is a record of what the reader was
shown.

A cited label that resolves to no loaded entry SHALL be reported as such, never matched to the
nearest one. Two loaded values with the same label SHALL stop the load with a message naming the
label; by the rule above it cannot happen, and if it does a guess would cite the wrong value.

#### Scenario: The store is loaded
- **WHEN** the agent's corpus is read from the store
- **THEN** it holds one entry per curated row and one per harvested value
- **AND** harvested values from every domain are present

#### Scenario: An answer cites a harvested value
- **WHEN** an answer rests on a harvested value
- **THEN** it cites it by its label, in the delimited form
- **AND** the citation is read back as that entry
- **AND** what is saved about the answer holds the store's identifier for that value

#### Scenario: One paper extracted twice
- **WHEN** the store holds two extractions of one paper, each with a first value
- **THEN** both values are entries, with distinct labels
- **AND** the earlier extraction's value keeps the unsuffixed label

#### Scenario: A saved answer outlives a later extraction
- **WHEN** an answer citing a harvested value was saved, and the same paper is extracted again
- **THEN** the saved answer still names the value it cited, by the store's identifier
- **AND** that identifier still resolves to the value as it was when the answer was given

#### Scenario: An older extraction arrives later
- **WHEN** an answer was saved citing a value, and an extraction of the same paper made earlier than
  that value's is then added to the store and loaded
- **THEN** the value the answer cited keeps its label, and the added extraction is the one suffixed
- **AND** the saved answer still resolves, by the store's identifier, to the value it cited

#### Scenario: A label that names nothing
- **WHEN** an answer cites a label no loaded entry carries
- **THEN** the citation is reported as naming no entry
- **AND** no other entry is substituted for it

#### Scenario: Two values claim one label
- **WHEN** two loaded harvested values would carry the same label
- **THEN** the load stops and names the label
- **AND** neither value is silently dropped

### Requirement: A harvested entry carries what a reader needs to judge it

A harvested entry SHALL carry: the property as the paper words it; the organism; the value as the
paper wrote it, with its unit; the passage the value was taken from; every condition the paper
states, each with the passage that states it; the name of every condition the extraction looked for
and the paper does not state; the paper's title, year, DOI, PMID, licence, domain and topic; and
whether the value was measured, calculated by the paper's authors, or calculated from values
published elsewhere.

A calculated value SHALL carry the passages it was calculated from, and SHALL be presented to the
model as a calculation, not as a measurement. A number a paper derives from three others is a
different kind of evidence from one it measured, and the difference is invisible once both are a
row in a table.

A condition the paper does not state SHALL be presented as not stated, never omitted and never
filled in. "Temperature not reported" is a fact about the source a reader can use; an absent line is
not.

The property the extraction was asked about SHALL NOT be presented as the entry's property: it is
the extraction's wording, not the paper's.

A keyword search SHALL reach a harvested entry's supporting passage and the passages of its stated
conditions, its domain and its topic. The paper's own wording of a property is often the shorter
one — "F-actin concentration" for a value measured in lamellipodia — and the qualifier a reader
searches for lives in the passage.

#### Scenario: A measured value is retrieved
- **WHEN** a harvested value the paper measured is retrieved in full
- **THEN** its property, organism, value, unit, supporting passage, stated conditions and paper are
  all presented
- **AND** it is identified as measured

#### Scenario: A calculated value is retrieved
- **WHEN** a harvested value the paper calculated is retrieved in full
- **THEN** it is identified as calculated, and by whom
- **AND** the passages it was calculated from are presented with it

#### Scenario: A qualifier found only in the passage
- **WHEN** a keyword search uses a term that appears in a harvested entry's supporting passage but
  not in its property
- **THEN** that entry is among the matches

#### Scenario: A condition is not stated
- **WHEN** the paper does not state a condition the extraction looked for
- **THEN** that condition is presented by name as not stated

### Requirement: A harvested value is stated as the paper wrote it, and as a number only where its reading is sure

A harvested value SHALL be presented in the words the paper used. The numbers read from it SHALL be
used for search, for presenting a range as a range, and for the dimensional comparison of values.

Where the numbers read from a value do not fit the kind of value the extraction recorded — two
numbers for a single value, one for a range, a central value with a range around it that the reading
does not keep — or where the value states a bound (`>500`, "up to 260", "at least 14") or holds a
number the reading did not use ("70 and 100"), the entry SHALL carry a caution saying the value
could not be read with certainty,
and SHALL NOT be presented to the model as a number it may state. Its text SHALL still be presented,
and the entry SHALL still be citable.

The two directions do not cost the same. A caution on a value read correctly costs a sentence; a
misread value stated with confidence is a wrong number that looks like every right one. So the
caution goes where the two disagree, whichever is wrong.

#### Scenario: A value with an uncertainty
- **WHEN** a harvested value is written as a number with an uncertainty
- **THEN** the number and its uncertainty are presented as the paper wrote them

#### Scenario: A value that states a bound
- **WHEN** a harvested value recorded as a single value is written as a bound, such as `>500 nm`
- **THEN** the entry carries a caution that its value could not be read with certainty
- **AND** no number is presented to the model as one it may state

#### Scenario: A unit that holds a scale factor
- **WHEN** a harvested value `5` has the unit `x 10^6 cells/mL`
- **THEN** the number read is 5, in that unit

#### Scenario: A reading that does not fit the recorded kind
- **WHEN** the numbers read from a value disagree with the kind of value the extraction recorded
- **THEN** the entry carries a caution that its value could not be read with certainty
- **AND** the paper's text is what is presented as its value

### Requirement: Nothing written for the review reaches the agent

The agent SHALL NOT be handed the text the review shows a reviewer beside a value to test them, nor
anything a reviewer wrote — a comment, an issue, the value they read. The agent SHALL be told only
an entry's trust tier, whether it is disputed, and whether the tier was set by a simulated review.

The test text is chosen to look like the right passage and is not one; handed to the model it is
evidence for the wrong value. A reviewer's words are text a stranger wrote, and the agent must not be
able to read it even by accident — the same line `answer-feedback` draws around a reader's comment.

#### Scenario: A harvested entry is retrieved
- **WHEN** a harvested entry is retrieved in full
- **THEN** none of the review's test text and none of any reviewer's words is in what the agent
  receives
- **AND** its tier, whether it is disputed and whether the tier is simulated are

### Requirement: The agent is told each entry's trust tier

Every entry the agent is shown from the store, in a search row and in full, SHALL carry its trust
tier on one scale, whether it is disputed, and whether the tier was set by a simulated review. The
tier is read by the rule recorded in ADR-0990 and SHALL NOT be computed a second way for the agent.

The agent SHALL be instructed to decide which entries bear on the question before weighing their
tiers, and that a tier never makes an entry relevant; then, among relevant entries for the same
quantity, to prefer the better-reviewed one. The agent SHALL be instructed not to mention an
entry's rating, approval or dispute in its answer -- the application shows them beside each
citation, and the same fact in prose says it twice -- unless the reader asks about that entry's
rating, review or objections. Trust is a property of an entry and relevance a property of an entry and the
question: told only to prefer trusted entries, a model can lead with a five-star value about a
neighbouring quantity over the two-star value that answers the question.

#### Scenario: Entries of different tiers conflict
- **WHEN** a search returns entries of different tiers for the same quantity
- **THEN** each row the agent sees carries its tier

#### Scenario: A trusted entry about another quantity
- **WHEN** the agent is given its instructions
- **THEN** they say that relevance to the question is decided first and that a tier does not make
  an entry relevant

#### Scenario: An answer rests on a disputed entry
- **WHEN** a cited entry is disputed
- **THEN** the agent was told it is disputed when it retrieved it

#### Scenario: The answer does not restate what the stars show
- **WHEN** the agent is given its instructions
- **THEN** they say not to mention ratings, approvals or disputes in the answer
- **AND** they say to answer from the trust line when the reader asks about an entry's rating

### Requirement: A harvested entry's reference is shown in Chicago author-date

Where the store holds a paper's bibliographic record as CSL-JSON, every harvested entry from that
paper SHALL be shown to the reader -- in the entries table's Reference column and in the full entry
-- with a reference in Chicago author-date form, its authors included, and its title as the paper
wrote it. Where the store holds no record, or one that cannot be formatted faithfully (no author, a
collaboration's name), the entry's plain reference SHALL be shown instead. The agent SHALL NOT be
given the formatted reference or the paper's authors: it is told to name no paper, and the names
are not its to write. A store written before it held these records SHALL load as before.

#### Scenario: A paper with its record
- **WHEN** a cited entry's paper has a CSL-JSON record with authors
- **THEN** its Reference reads in Chicago author-date, surname first for the first author, the
  year after the names, and the title unchanged in case

#### Scenario: A paper without one
- **WHEN** a cited entry's paper has no record, or one with no author
- **THEN** its Reference is the title, year and DOI, as before

#### Scenario: The agent retrieves the entry
- **WHEN** the agent retrieves an entry whose paper has a record
- **THEN** nothing it is shown names the paper's authors or journal
