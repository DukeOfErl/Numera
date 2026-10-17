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

## MODIFIED Requirements

### Requirement: A harvested entry names its quantity, its class and what it belongs to

Each entry SHALL carry labels written by the model and not quoted: what was measured, what it is
a measure of, one of the domain's classes, and the organism — as the Latin binomial wherever the
article gives one — or, for a value that belongs to no organism, the material or system as the
article names it. The value field SHALL hold no unit.

The entry's property SHALL be one name that says both what was measured and of what — "Average
length of F-actin filaments in non-contracting rings", never "average length" nor "cytokinetic
actin rings" alone. The system SHALL join the two parts the model writes into that name, and
SHALL refuse an entry whose parts do not make one: a part missing, or one part repeating the
other. A refused entry SHALL be dropped and recorded by its identifier, not kept under the
article's own term.

Where an article reports the same quantity under more than one condition, the object of every
value but the article's control SHALL end with its condition as a scientist would name it — growth
state, genotype or construct, tissue, developmental stage, position, or outside biology the sample
or state — and never as a table's row or column label. The value the article marks as its control
or wild type SHALL carry no condition in its name.

An entry stored before the two parts were asked for SHALL be named on request from what the store
holds of it — its quote, value, unit, conditions and labels — without re-reading the article, and
without rewriting the record a reviewer was shown.

#### Scenario: Two conditions of one quantity
- **WHEN** an article reports a ring spacing for two constructs
- **THEN** the two entries are named by their constructs, not both by the bare quantity

#### Scenario: A glass
- **WHEN** a value belongs to a material rather than an organism
- **THEN** the entry is labelled with the material

#### Scenario: A bare measure or a bare object
- **WHEN** the model names a value "average length" with nothing it is a length of, or
  "cytokinetic actin rings" with nothing measured
- **THEN** the entry is dropped and its identifier recorded

#### Scenario: A store named earlier
- **WHEN** a store holds entries with no property name and the naming is requested
- **THEN** each such entry is named from its own record, an entry already named is left as it
  is, and no entry's stored record changes
