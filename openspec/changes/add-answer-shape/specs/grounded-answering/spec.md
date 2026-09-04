## ADDED Requirements

### Requirement: An answer leads with its quantitative conclusion

An answer that states a quantity SHALL open with the quantity asked for, before any explanation,
caveat, method or discussion of the corpus. The opening SHALL cite the entries its figure comes from,
in the stated citation form.

Where the quantity genuinely varies, the opening SHALL give the range, or a typical value together
with the condition it holds under, and SHALL name what the quantity varies with. Variation is the
answer to such a question and SHALL NOT be treated as a reason to withhold a figure: an answer
SHALL NOT open by stating only that the quantity has no single value, unless the same opening also
gives the range or typical value that does answer the question.

Where a summary figure is drawn from several entries, it SHALL use those entries' own recorded
numbers rather than rounded approximations of them, and SHALL cite each entry whose figure it uses.
Rounding a recorded 0.47 to 0.5 for a tidier opening claims a precision the corpus does not carry,
and puts the answer's headline outside the agreement any check of the figure against its entry would
apply.

A reader who wants the number and stops after the first line must get the number. Every other
requirement in this capability pushes toward qualification — cite everything, do not present one
entry as settled, report disagreement with its conditions, mark what the source did not claim — and
together they produce prose that opens with caveats because nothing asks it to open with the finding.

#### Scenario: A question the corpus covers well
- **WHEN** an answer states a quantity for a question the corpus supports
- **THEN** its opening gives that quantity
- **AND** the opening cites the entries the figure comes from

#### Scenario: A quantity that varies with conditions
- **WHEN** the entries for a question record values that vary with a condition
- **THEN** the opening gives the range or a typical value with its condition
- **AND** names what the quantity varies with

#### Scenario: Variation is not a reason to withhold the figure
- **WHEN** an answer's opening states that the quantity has no single value
- **THEN** the same opening also gives the range or typical value that answers the question

#### Scenario: A summary figure across entries
- **WHEN** an opening gives a range drawn from several entries
- **THEN** it uses those entries' recorded numbers rather than rounded approximations
- **AND** cites each entry whose figure it uses

### Requirement: Leading with a figure does not displace what qualifies it

An answer's opening SHALL NOT be achieved by omitting anything the rest of this capability requires.
The conditions that distinguish disagreeing entries, the hedges the source recorded, what an entry
did not claim, and the inputs behind a computed figure SHALL all still appear in the answer, below
the opening.

Where a figure in the opening is qualified — an approximate value, a one-sided bound, an entry with
no recorded method — the opening SHALL carry the qualification with it rather than leaving it to be
found further down. A qualification that arrives only after the reader has stopped reading has not
been given.

This requirement exists because the one before it can be satisfied cheaply and wrongly. A crisp
first line bought by dropping the caveats would trade the property this project is built on for
readability, and the two failures are hard to tell apart from the opening alone.

#### Scenario: An opening figure that the source hedged
- **WHEN** the figure in an answer's opening comes from an entry recording an approximate value or a one-sided bound
- **THEN** the opening states the figure as approximate or as a bound

#### Scenario: Disagreement behind a summary opening
- **WHEN** an opening summarises entries that disagree
- **THEN** the conditions distinguishing them appear in the answer below the opening

#### Scenario: The opening omits nothing that is required
- **WHEN** an answer opens with its conclusion
- **THEN** every qualification the rest of this capability requires still appears in the answer
