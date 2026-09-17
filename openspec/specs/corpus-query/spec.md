# corpus-query Specification

## Purpose
Gives the agent a bounded, read-only way to look things up in a corpus of quantities: find candidate
entries, read one in full, and discover what vocabulary the corpus actually uses. The surface is
deliberately small, because every tool is a way for the agent to go wrong.
## Requirements
### Requirement: Search returns compact rows, bounded in number

Search SHALL return a capped number of compact rows rather than full entries, and SHALL report how
many entries matched in total so the caller knows the result was truncated. A compact row SHALL
carry at least the entry identifier, property, organism, value or range, and units.

Common single-word searches match hundreds to over a thousand entries in the reference corpus;
returning full entries would exhaust the context window on a single call and would bury the
selection decision the agent needs to make.

#### Scenario: Search matches more entries than the cap
- **WHEN** a search matches more entries than the result cap
- **THEN** the capped set of compact rows is returned
- **AND** the total number of matches is reported alongside them

#### Scenario: Search matches nothing
- **WHEN** a search matches no entries
- **THEN** an empty result is returned with a total of zero
- **AND** no entries are invented or approximated to fill it

### Requirement: A stored value is presented as what it measures

A value SHALL be presented as the single number it is where the corpus stores one measurement as a
range whose bounds are equal, rather than reproduced literally as a range. 1,403 of the reference
corpus's entries are stored that way; rendered literally, "400.0-400.0" invites a reader to look for
a spread that is not there, and reaches the model as one too.

A range whose bounds genuinely differ SHALL be presented as a range, and a half-open range SHALL NOT
be rendered with a missing bound.

#### Scenario: A single measurement stored as a range
- **WHEN** an entry's lower and upper bounds are equal
- **THEN** the value is presented as one number

#### Scenario: A genuine range
- **WHEN** an entry's bounds differ
- **THEN** both are presented

### Requirement: A search records which entries it returned

A search SHALL record the identifiers of the entries it returned, not only how many matched and how
many were returned.

Without them, an answer's citations cannot be checked against what the agent was actually shown, and
a citation drawn from the model's own memory is indistinguishable from one drawn from the corpus.
They are also what lets a driver present the entries behind an answer without asking the corpus a
second question.

#### Scenario: A search returns rows
- **WHEN** a search returns rows
- **THEN** the identifiers of those rows are recorded
- **AND** they are available to a driver without re-running the search

### Requirement: Organism and property matching is tolerant, not exact

Search SHALL match organism and property terms case-insensitively against substrings of the stored
values, and SHALL NOT require an exact match against a canonical term.

The reference corpus holds 841 distinct organism strings at inconsistent taxonomic levels — species
written as a common name followed by a binomial (`Bacteria Escherichia coli`), bare group names
(`Mammals`, `Eukaryotes`, `bacteria`), and non-taxonomic placeholders (`Generic`, `Unspecified`,
`Biosphere`) covering 14% of entries. Exact matching would return nothing for the terms a user
naturally types.

#### Scenario: User's term is a substring of the stored organism
- **WHEN** a search specifies the organism term `coli`
- **THEN** entries whose organism is `Bacteria Escherichia coli` are matched

#### Scenario: Stored organism differs only in case
- **WHEN** a search specifies the organism term `Bacteria`
- **THEN** entries whose organism is stored as `bacteria` are matched alongside those stored as `Bacteria …`

#### Scenario: Term matches at a broader taxonomic level
- **WHEN** a search term matches both a group-level organism and species-level organisms
- **THEN** all of them are returned
- **AND** each row carries its own organism string so the caller can tell them apart

### Requirement: A keyword search reaches an entry's own keywords

Search SHALL accept a keyword term and match it against both an entry's curated keywords and its
property, matching either. Matching SHALL ignore case on both sides.

Curated keywords carry wordings the property does not — `radius` against a property called
`Cell diameter` — and are the corpus's own record of what an entry is about. A keyword search that
reached only the property would duplicate property search and find nothing new; one that reached only
the keywords would miss the entries whose property already says it.

#### Scenario: A term appearing only in an entry's keywords
- **WHEN** a keyword search uses a term stored in an entry's keywords and absent from its property
- **THEN** that entry is returned

#### Scenario: A term appearing only in a property
- **WHEN** a keyword search uses a term present in an entry's property and absent from its keywords
- **THEN** that entry is returned

#### Scenario: A term whose case does not match what is stored
- **WHEN** a keyword search uses a term differing only in case from what the corpus stores
- **THEN** the same entries are returned

### Requirement: The corpus vocabulary is discoverable

The system SHALL provide a way to list the organism and property values present in the corpus,
filtered by a partial term. The agent SHALL NOT be required to guess a stored value's exact wording
in order to find entries.

Without this, an agent searching for `E. coli` against a corpus that stores
`Bacteria Escherichia coli` receives zero results and has no way to tell an absent topic from a
wrong guess.

Values SHALL be returned commonest first. The order carries meaning here: it tells the agent which
wording the corpus actually uses, which is the question being asked whenever this is reached for.
Alphabetical order would put a wording used once above one used two thousand times.

#### Scenario: Listing organism values matching a partial term
- **WHEN** the agent asks for organism values matching `yeast`
- **THEN** the distinct stored values containing that term are returned with their entry counts
- **AND** the value with the most entries comes first

#### Scenario: Listing property values
- **WHEN** the agent asks for property values matching a partial term
- **THEN** those are listed on the same terms as organisms
- **AND** properties are the harder half to guess, so this is not an organism-only facility

#### Scenario: Distinguishing an absent topic from a failed guess
- **WHEN** a search returns nothing
- **THEN** the vocabulary listing is available to establish whether the corpus covers the topic under different wording

### Requirement: Common naming variants resolve without a round trip

The system SHALL carry a deterministic index mapping common naming variants to the values stored in
the corpus, built from the corpus itself and shared across all sessions. Search SHALL consult it, so
that a widely used abbreviation resolves to the stored value without the agent first having to
discover the corpus's wording.

This index is deliberately deterministic and shared rather than learned per user. It is the same
mapping for everyone, it can be inspected and corrected, and a search that used it can be explained.
Accumulating the same knowledge as per-session memory would make retrieval vary between users for no
benefit, and make a wrong mapping invisible.

#### Scenario: A common abbreviation is used
- **WHEN** a search uses a widely used short form of an organism name, such as `E. coli`
- **THEN** entries stored under the corpus's own wording for that organism are matched

#### Scenario: The index is inspected
- **WHEN** the index is examined
- **THEN** each mapping and the stored value it resolves to can be read
- **AND** a mapping can be corrected without retraining or replaying any session

#### Scenario: A term is not in the index
- **WHEN** a search term has no mapping
- **THEN** matching proceeds on the term as given
- **AND** vocabulary discovery remains available to establish the corpus's wording

### Requirement: Full entries are retrieved individually and expose their cross-references

The system SHALL retrieve a complete entry by identifier, including its reference, measurement
method, and comments. Where an entry's text cites other entries by identifier, those identifiers
SHALL be exposed as a parsed list on the retrieved entry.

Cross-references are real but sparse — 11% of entries in the reference corpus cite at least one
other, most citing exactly one — so they are surfaced as data on the entry rather than as a separate
traversal tool.

#### Scenario: Entry cites other entries
- **WHEN** a retrieved entry's comments cite other entries by identifier
- **THEN** those identifiers are returned as a parsed list
- **AND** each can be retrieved with the same entry-retrieval call

#### Scenario: Entry cites nothing
- **WHEN** a retrieved entry cites no other entries
- **THEN** the parsed list is empty

### Requirement: The corpus is read-only

No tool exposed to the agent SHALL create, modify, or delete corpus entries.

#### Scenario: Agent attempts to record something
- **WHEN** the agent has completed an answer
- **THEN** no corpus entry has been created, modified, or deleted

### Requirement: An entry handed to the model carries one citation notation

Where an entry's own text cites other entries in the source's notation, the copy handed to the model
SHALL restate those citations in the form the model is asked to write. The stored corpus SHALL NOT be
altered, and every surface presented to a person SHALL keep the source's text as written.

An entry's prose is the most likely reason for a model to answer in a notation it was not asked for:
it is shown one form and instructed to produce another in the same exchange, and it is the corpus
that puts the first one there. Restating it where the text is rendered removes that cause without
editing the evidence — the stored entry remains what the source published, which is what makes a
figure traceable and what a view of the unprocessed entry would show.

Text that is not an identifier SHALL pass through unchanged. A restatement that converted something
the source did not write as an identifier would manufacture a citation.

Any list of an entry's cross-references presented to the model SHALL use the same form. Bare
identifiers are citations in no notation, unusable by a model instructed to cite in one.

#### Scenario: An entry citing others is retrieved
- **WHEN** an entry whose text cites other entries is handed to the model
- **THEN** those citations appear in the form the model is asked to write
- **AND** the stored entry still holds the source's text

#### Scenario: A person reads the same entry
- **WHEN** an entry is presented to a person
- **THEN** the source's own notation is shown, naming the database the identifier belongs to

#### Scenario: The source wrote something that is not an identifier
- **WHEN** an entry's text contains a marker followed by something that is not an identifier
- **THEN** that text is passed through exactly as written

### Requirement: A corpus written to a superseded contract is refused by name

Where a corpus was produced against an earlier version of the record contract, the system SHALL
refuse it with a message naming what changed and what the reader must do. It SHALL NOT report the
condition as an unreadable or malformed corpus, and SHALL NOT silently accept the earlier form.

A corpus is not rebuilt once it exists, so such a file reaches the loader on every start with nothing
in the system able to repair it. The reader is the only party who can act, and a message naming a
missing field tells them neither what happened nor what to do.

The refusal SHALL be reported through the same channel as every other unavailable corpus, so drivers
need no special handling.

A corpus that is unreadable for any other reason SHALL NOT be reported as one written to a superseded
contract. Told their corpus is a version behind, a reader would rebuild a corpus whose actual problem
is malformation and be given the same file back.

#### Scenario: A corpus keyed the earlier way
- **WHEN** a corpus whose records carry the superseded identifier key is loaded
- **THEN** it is refused
- **AND** the message names the file, what changed, and how to produce a current one

#### Scenario: A record that carries no identifier at all
- **WHEN** a corpus record carries neither the current nor the superseded identifier key
- **THEN** it is reported as an unusable record
- **AND** it is not attributed to a superseded contract

