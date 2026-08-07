## Purpose

Turns a quantity's claimed reference into machine-readable full text that can be examined for
supporting evidence, or into an explicit, typed reason why no such text could be obtained. Access
failures are first-class results here, because a claim that could not be checked must never be
confused with a claim that was checked and failed.

## ADDED Requirements

### Requirement: Reference resolution to a persistent identifier

The system SHALL resolve a quantity's claimed reference to a persistent document identifier before
attempting retrieval. WHERE no identifier can be determined, the system SHALL record a typed
resolution failure rather than attempting a best-guess retrieval.

#### Scenario: Reference carries a persistent identifier
- **WHEN** an entry's reference includes a persistent article identifier
- **THEN** the system resolves the reference to that identifier
- **AND** proceeds to retrieval

#### Scenario: Reference is a book, thesis, or other non-article source
- **WHEN** an entry's reference names a source that has no persistent article identifier
- **THEN** the system records the typed reason `NON_ARTICLE_SOURCE`
- **AND** does not attempt retrieval

#### Scenario: Reference cannot be resolved
- **WHEN** an entry's reference is free text from which no identifier can be determined
- **THEN** the system records the typed reason `UNRESOLVED_REFERENCE`

### Requirement: Retrieval restricted to openly accessible sources

The system SHALL retrieve full text only from sources that are openly accessible and whose licence
permits automated text analysis. The system SHALL NOT circumvent access controls, paywalls, or
rate limits to obtain text.

#### Scenario: Open-access full text is available
- **WHEN** the resolved document is available as openly accessible full text
- **THEN** the system retrieves the full text

#### Scenario: Only metadata or an abstract is available
- **WHEN** the resolved document exposes only bibliographic metadata or an abstract
- **THEN** the system records the typed reason `NO_FULL_TEXT`
- **AND** does not treat the abstract as full text

#### Scenario: Document is paywalled
- **WHEN** the resolved document's full text is behind an access restriction
- **THEN** the system records the typed reason `NO_OPEN_ACCESS`
- **AND** makes no attempt to bypass the restriction

### Requirement: Preprint substitution is permitted and always disclosed

WHERE the version of record is not openly accessible but a preprint of the same work is, the system
SHALL retrieve the preprint. The system SHALL record which artifact was actually examined, including
whether it was a preprint and which version, so that a value differing between preprint and
published article is attributable to version drift rather than to a validator defect.

#### Scenario: Preprint substituted for an inaccessible article
- **WHEN** the version of record is not openly accessible
- **AND** an openly accessible preprint of the same work exists
- **THEN** the system retrieves the preprint
- **AND** records the retrieved artifact as a preprint together with its version

#### Scenario: Version of record is accessible
- **WHEN** the version of record is openly accessible
- **THEN** the system retrieves the version of record in preference to any preprint
- **AND** records the retrieved artifact as the version of record

### Requirement: Retrieved documents preserve structure and locatable spans

The system SHALL preserve the structural organisation of a retrieved document, including sections,
paragraphs, tables, and captions. Every span of retrieved text SHALL carry a stable location
reference sufficient to cite it and to return to it later.

#### Scenario: Value appears in body text
- **WHEN** a span is located in a paragraph of the document body
- **THEN** its location reference identifies the containing section and paragraph

#### Scenario: Value appears in a table
- **WHEN** a span is located inside a table
- **THEN** its location reference identifies the table and the cell

#### Scenario: Content is available only as an image
- **WHEN** part of a document's content exists only within a figure image
- **THEN** the system marks that content as not machine-readable
- **AND** does not treat its absence from the text as evidence about any claim

### Requirement: Unavailability is typed and never silent

Every reference that cannot be resolved or retrieved SHALL be recorded with a machine-readable
reason drawn from a closed set. The system SHALL NOT discard an entry, and SHALL NOT substitute a
generic failure for a specific known cause.

#### Scenario: Entry cannot be retrieved
- **WHEN** any resolution or retrieval step fails
- **THEN** the entry is retained with a typed reason recorded
- **AND** the entry is not dropped from downstream reporting

#### Scenario: Counting unavailable entries
- **WHEN** a caller asks how many entries were unavailable
- **THEN** the system reports counts broken down by typed reason
