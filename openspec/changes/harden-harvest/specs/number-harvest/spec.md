## ADDED Requirements

### Requirement: An article yields at most twenty entries, and a drop is recorded

The system SHALL keep at most twenty entries from one article in one run, whatever the model
returns. Entries beyond the twentieth SHALL be dropped before any further model call is made for
them, and the article's record SHALL say how many were dropped.

#### Scenario: The model returns more than twenty

- **WHEN** the extraction call for an article returns thirty verified entries
- **THEN** twenty are kept, in the order the model gave them
- **AND** no second-text call is made for the other ten
- **AND** the article's record says ten were dropped by the bound

#### Scenario: Twenty or fewer

- **WHEN** an article yields twenty entries or fewer
- **THEN** all are kept and the record says none were dropped

### Requirement: A comment in a list of articles is a comment wherever it starts

When a run reads its articles from a list, the system SHALL treat a line whose first non-blank
character is `#` as a comment, and SHALL never take `#` as an article identifier.

#### Scenario: An indented comment

- **WHEN** the list holds `PMC1234567`, `  # planarians` and `PMC7654321`
- **THEN** the run reads exactly the two identifiers
