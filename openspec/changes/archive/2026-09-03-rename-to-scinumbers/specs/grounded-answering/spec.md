## MODIFIED Requirements

### Requirement: Citations use one stated format

Entry identifiers SHALL be written in a single stated form wherever they appear in an answer. The
form SHALL be given to the model as an instruction, and SHALL be **delimited** — carrying a mark
where the identifier ends as well as where it begins. Parsing SHALL NOT infer an identifier from a
bare number.

Three reasons now. A reader comparing several answers should see citations look the same every time.
A bare six-digit number is indistinguishable from a six-digit quantity, so a parser without a marker
cannot tell a citation from a measurement. And a form that marks only its start forces the parser to
infer where the identifier ends — which requires rules about the identifier's own shape, each of
which is a place a corpus with differently shaped identifiers would break.

The instruction given to the model SHALL be produced from the same definition the parser uses, not
restated alongside it. A prompt asking for a form the parser does not read produces answers reported
as uncited, with nothing failing.

Parsing MAY additionally accept a form the system does not ask for, where readers are known to
introduce it. A reader familiar with the source's own notation writes it in their question; a
session's follow-up questions inherit the conversation, so from that point the model answers in it.
Rejecting it would report well-cited answers as unsupported, and a false negative here is worse than
the ambiguity that accepting it admits. Where a second form is accepted, identifiers SHALL be
ordered by where they appear in the text rather than grouped by which form wrote them.

A delimited group that holds no identifier SHALL be recorded rather than discarded silently. An
answer that tried to cite and failed is otherwise indistinguishable from one that never tried.

#### Scenario: An answer cites an entry
- **WHEN** an answer rests on an entry
- **THEN** the identifier appears in the stated form
- **AND** the same form is used for every identifier in that answer

#### Scenario: A quantity resembles an identifier
- **WHEN** an answer states a quantity whose digits could be read as an identifier
- **THEN** it is not parsed as a citation
- **AND** only delimited identifiers are counted

#### Scenario: The instruction and the parser cannot disagree
- **WHEN** the citation form changes
- **THEN** the instruction given to the model changes with it

#### Scenario: A reader introduces the source's own notation
- **WHEN** an answer cites an identifier in a notation the reader used rather than the stated form
- **THEN** the citation is still counted
- **AND** it is ordered among the others by where it appears

#### Scenario: A citation that cannot be read
- **WHEN** an answer contains a delimited group holding no identifier
- **THEN** it is not counted as a citation
- **AND** the occurrence is recorded

#### Scenario: An identifier that was never retrieved
- **WHEN** an answer cites an identifier that no tool call returned
- **THEN** this is detectable from the emitted events
- **AND** it is reported rather than accepted
