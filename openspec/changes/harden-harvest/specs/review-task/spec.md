## ADDED Requirements

### Requirement: Readings of one article from different runs are served together and linked

An article extracted in more than one run SHALL remain one article to a reviewer and a reader.
The system SHALL serve a reviewer the items of one article together across runs, as it does
within one run, and an entry SHALL show that its article has other readings, and which of them
report the same property with a different value. No reading SHALL be merged into another or
dropped for being a repeat.

#### Scenario: Two runs read the same article

- **WHEN** runs A and B both extracted article P, and a reviewer is served an item of P from run A
- **THEN** the reviewer's next items include P's items from run B before any other article's, unless
  every one of them is already decided by that reviewer

#### Scenario: The readings disagree

- **WHEN** run A reports a property of P as 4.2 and run B reports the same property as 4.7
- **THEN** each of the two entries shows that P was read twice and names the other reading's value

#### Scenario: Nothing is merged

- **WHEN** the two runs report the same property with the same value
- **THEN** both entries remain, each with its own identifier, and each shows the other as agreeing
