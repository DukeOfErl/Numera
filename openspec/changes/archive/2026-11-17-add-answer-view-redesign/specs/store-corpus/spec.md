## MODIFIED Requirements

### Requirement: A harvested entry's reference is shown in Chicago author-date

Where the store holds a paper's bibliographic record as CSL-JSON, every harvested entry from that
paper SHALL be shown to the reader -- in the full entry, and as its first author and year in the
entries table -- with a reference in Chicago author-date form, its authors included, and its title as the paper
wrote it. Where the store holds no record, or one that cannot be formatted faithfully (no author, a
collaboration's name), the entry's plain reference SHALL be shown instead. The agent SHALL NOT be
given the formatted reference or the paper's authors: it is told to name no paper, and the names
are not its to write. A store written before it held these records SHALL load as before.

#### Scenario: A paper with its record
- **WHEN** a cited entry's paper has a CSL-JSON record with authors
- **THEN** the opened entry's reference reads in Chicago author-date, surname first for the first
  author, the year after the names, and the title unchanged in case
- **AND** its row in the table names the first author and the year

#### Scenario: A paper without one
- **WHEN** a cited entry's paper has no record, or one with no author
- **THEN** its reference is the title, year and DOI, as before

#### Scenario: The agent retrieves the entry
- **WHEN** the agent retrieves an entry whose paper has a record
- **THEN** nothing it is shown names the paper's authors or journal
