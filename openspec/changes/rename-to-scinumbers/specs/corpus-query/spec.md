## ADDED Requirements

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
