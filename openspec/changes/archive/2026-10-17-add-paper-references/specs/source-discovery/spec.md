## ADDED Requirements

### Requirement: The bibliographic record travels with the paper

For every fetched document, the system SHALL read from its front matter the bibliographic record
needed to cite it -- its authors in the paper's order, the journal, the volume, the issue, the
pages or article number, the publication date and its identifiers -- and SHALL keep it with the
paper as one CSL-JSON item. Only what the front matter states SHALL be recorded. Editors and
reviewers SHALL NOT be recorded as authors. The citation shown to a reader SHALL be formatted from
this record by the application, never written by a model.

A record kept before this requirement existed SHALL be filled from the cached full text on
request, without re-extracting anything.

#### Scenario: The authors, and only the authors
- **WHEN** a document names its authors on each contributor or on the contributor group, and
  names an editor or a reviewer in another group
- **THEN** the record lists the authors in the paper's order and nobody else

#### Scenario: A collaboration
- **WHEN** an author is a named collaboration rather than a person
- **THEN** the record carries it as one literal author

#### Scenario: Pages or an article number
- **WHEN** a document states a first and last page, a first page alone, or an article number
- **THEN** the record carries the range, the page, or the article number respectively

#### Scenario: The article's own date
- **WHEN** a document states a volume's collection date and the article's own publication date
- **THEN** the record's date is the article's own, and the paper's year agrees with it

#### Scenario: A store loaded earlier
- **WHEN** a store holds papers from before the record was kept and the full text is in the cache
- **THEN** each such paper's record is filled from its front matter, and a paper already holding
  one is left as it is
