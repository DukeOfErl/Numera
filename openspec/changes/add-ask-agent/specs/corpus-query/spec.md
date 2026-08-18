## Purpose

Gives the agent a bounded, read-only way to look things up in a corpus of quantities: find candidate
entries, read one in full, and discover what vocabulary the corpus actually uses. The surface is
deliberately small, because every tool is a way for the agent to go wrong.

## ADDED Requirements

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

### Requirement: The corpus vocabulary is discoverable

The system SHALL provide a way to list the organism and property values present in the corpus,
filtered by a partial term. The agent SHALL NOT be required to guess a stored value's exact wording
in order to find entries.

Without this, an agent searching for `E. coli` against a corpus that stores
`Bacteria Escherichia coli` receives zero results and has no way to tell an absent topic from a
wrong guess.

#### Scenario: Listing organism values matching a partial term
- **WHEN** the agent asks for organism values matching `yeast`
- **THEN** the distinct stored values containing that term are returned with their entry counts

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
