## Purpose

Turns one raw row of the published export into one canonical measurement record, resolving the
notations, glyph variants and injected markup the source actually contains. A wrong number here
reaches the reader as a cited measurement and looks correct, so each rule the source forced on us is
stated as behaviour rather than left to the code.

## ADDED Requirements

### Requirement: A range is normalized to a low and a high bound

The source writes ranges several ways. The system SHALL read all of the following as a low and a
high bound: a hyphen (`0.44-1.79`), the word `to` (`1.94 to 2.72`), an en or em dash (`1–2`), and
any of these with negative bounds.

The source also prefixes `Range` cells with an Excel text-marker apostrophe. The system SHALL strip
it, and SHALL preserve the cell's original text alongside the parsed bounds so a reader can audit
what a number came from.

That preserved text is the source cell, not the string the bounds were computed from: for a row whose
range carries an external link, it retains the URL, whose escaped filename contains digits an
extractor would read as measurements. The system SHALL keep it that way — the audit value of the
field is that it is the source — and SHALL state at the field itself that a recomputation from it must
remove the link first. The link is separately available on the record, so nothing is lost either way.

#### Scenario: The preserved text retains a link

- **WHEN** a link-carrying row is emitted
- **THEN** its preserved range text still contains the link URL
- **AND** the parsed bounds contain no number taken from that URL

#### Scenario: Ranges in each notation

- **WHEN** a range cell reads `'1.94 to 2.72`, `'0.44-1.79`, or `'1–2`
- **THEN** the low and high bounds are the two numbers it names, in order

#### Scenario: The original text survives

- **WHEN** a range cell is parsed
- **THEN** the record carries the cell's text with the leading apostrophe removed

### Requirement: A sign is told apart from a separator

A hyphen in this source is sometimes a minus sign and sometimes a range separator, and reading one
as the other turns a membrane potential of `-70` into a range and `-90--60` into nonsense. The
system SHALL treat a hyphen as a separator only where it directly follows a digit, and SHALL treat
it as a sign otherwise. A unicode minus SHALL be read as a sign. The sign inside an exponent SHALL
never be read as a separator.

#### Scenario: A negative single value

- **WHEN** a range cell reads `'-70`
- **THEN** both bounds are `-70`

#### Scenario: Negative bounds

- **WHEN** a range cell reads `'-90 to -60`, `'-90--60`, or `'−5 to −1`
- **THEN** the bounds are `-90` and `-60`, or `-5` and `-1` respectively

#### Scenario: Scientific notation

- **WHEN** a range cell reads `'1.5e-3 to 4e-2`
- **THEN** the bounds are `0.0015` and `0.04`, and the exponent signs produce no extra numbers

### Requirement: Plus-or-minus is uncertainty, not a bound

`±Δ` in the range column is an uncertainty about the value column, written variously as `±`, `+-` or
`+/-`. The system SHALL read it as the interval from `value − Δ` to `value + Δ`, and SHALL record
that the range came from an uncertainty.

Where the value column is empty and the range cell is entirely one `mean±sd` expression, the system
SHALL recover the mean from the range cell and derive the same interval. Where the value column is
empty and the cell holds more than one measurement, the system SHALL record no bounds and flag the
row rather than collapsing several measurements into one range.

#### Scenario: Uncertainty around a value

- **WHEN** the value is `7.4` and the range cell reads `'±1.15`, `'+-1.15`, or `'+/-1.15`
- **THEN** the bounds are `6.25` and `8.55`
- **AND** the row is flagged as having come from a plus-or-minus range

#### Scenario: Mean and deviation in one cell, no value column

- **WHEN** the value is empty and the range cell reads `'-3.26±0.41`
- **THEN** the bounds are `-3.67` and `-2.85`
- **AND** the row is flagged as a recovered embedded mean

#### Scenario: Two measurements in one cell

- **WHEN** the value is empty and the range cell reads `'7.4±0.3 one face 5.9±0.3 other face`
- **THEN** no bounds are recorded
- **AND** the row is flagged as a plus-or-minus range with no value

### Requirement: A range that may fuse two quantities is flagged

Bounds are taken as the lowest and the highest number found in the range cell, so a cell that names
a second quantity — another measurement, a count, a duration — contributes a bound to the first, and
the result is a range that reads as one measurement and is not. The system SHALL mark such a cell
rather than correct it: bounds are computed unchanged, and the record carries a flag naming why it is
suspect.

Two conditions SHALL be flagged: a cell from which more than two numbers were read, and text
standing between the two numbers that became the bounds. A consumer SHALL be able to read the
presence of either flag as "this range is not usable as a measurement" without knowing which
condition applied.

Correcting the bounds is out of scope for this capability; see `proposal.md` — Deferred.

#### Scenario: More than two numbers in one cell

- **WHEN** a range cell yields more than two numbers
- **THEN** the bounds are still the lowest and the highest of them
- **AND** the record is flagged as having come from a cell with more than two numbers

#### Scenario: A second quantity named between the bounds

- **WHEN** a range cell names a second quantity between the two numbers that become the bounds
- **THEN** the record is flagged as having text between its bounds

#### Scenario: An ordinary two-number range is not flagged

- **WHEN** a range cell holds exactly two numbers separated only by a separator
- **THEN** neither flag is present

### Requirement: A row whose range is only a link is kept

About 23% of rows carry, in place of a scalar, a "Table link" URL to an external PDF. The system
SHALL preserve that URL on the record, SHALL flag the row, and SHALL NOT drop it. Digits inside the
URL SHALL NOT be read as measurements.

#### Scenario: A link with a range beside it

- **WHEN** a range cell reads `'0.44-1.79 Table link - http://example.org/E.%20coli%20volume.pdf`
- **THEN** the bounds are `0.44` and `1.79`
- **AND** the URL is preserved on the record
- **AND** no number from the URL appears in the bounds or units

#### Scenario: A link and nothing else

- **WHEN** a range cell holds only a "Table link" URL
- **THEN** the row is emitted with no value and no bounds
- **AND** the URL is preserved and the row is flagged as a link and as carrying no scalar

### Requirement: Units and text are normalized across the source's encodings

The source encodes micrometre with two different characters — the micro sign and the Greek letter
mu — which makes two entries in the same unit look like entries in different units. The system SHALL
normalize them to one character. HTML entities SHALL be unescaped and runs of whitespace collapsed,
in units and in every text field.

#### Scenario: The two micrometre glyphs

- **WHEN** two rows record units as the micro sign followed by `m` and as the Greek mu followed by `m`
- **THEN** both records carry the same unit string
- **AND** neither carries the micro sign

#### Scenario: An entity-encoded unit

- **WHEN** a units cell reads `&#181;m`
- **THEN** the record's unit is the normalized micrometre string

### Requirement: Injected markup is stripped and reported

Cells in the published export contain injected markup, including `<IMG SRC="/WF_SQL_XSRF.html">`.
The system SHALL remove markup from every field and SHALL flag any row from which markup was
removed, so contamination in the source is visible rather than quietly cleaned.

**The markup arrives HTML-escaped, and the order of operations therefore decides whether any of this
works.** In the published export the injected tags appear only as `&lt;IMG SRC="/WF_SQL_XSRF.html"&gt;`
— 20,411 occurrences, and not one literal `<IMG`. Unescaping entities after stripping tags therefore
*manufactures* markup into the output: the tag pattern matches nothing on the raw cell, and the
unescape then produces a live tag that nothing strips again. Computing the flag on the pre-unescape
text fails the same way, so the contamination is neither removed nor reported.

The system SHALL therefore unescape entities BEFORE removing markup, SHALL determine whether a row
carried markup from the unescaped text, and SHALL repeat the unescape-then-strip pass until the text
stops changing, so that multiply-escaped markup cannot survive one round.

This order SHALL be established at ONE cleaning boundary through which every field passes, not
repeated per field. In the published export the injected markup happens to appear only in the
`Keywords` column — but that is one sample of one file, and an absence observed in a sample is not an
absence. Any column could carry it in a later export, and `Range` is the one that would do real
damage: a manufactured tag there puts the digits of an escaped filename within reach of number
extraction, where they would raise the fused-range predicate and be indistinguishable from a genuine
fusion of two quantities.

#### Scenario: Escaped markup in any column is handled

- **WHEN** escaped markup is injected into each of the export's columns in turn
- **THEN** no field of the emitted record carries markup, for every column
- **AND** the row is flagged as having had markup removed, for every column
- **AND** no digit from the injected markup reaches a bound, a value or a unit

#### Scenario: Markup inside a keyword list

- **WHEN** a keywords cell reads `Cell size<IMG SRC="/WF_SQL_XSRF.html">`
- **THEN** the keywords are `Cell size` alone, with no markup in any of them
- **AND** the row is flagged as having had markup removed

#### Scenario: Escaped markup, which is the form the export actually uses

- **WHEN** a keywords cell reads `Cell size&lt;IMG SRC="/WF_SQL_XSRF.html"&gt;`
- **THEN** the keywords are `Cell size` alone, with no markup in any of them
- **AND** the row is flagged as having had markup removed, exactly as for the literal form

#### Scenario: No emitted field carries markup

- **WHEN** any record is emitted
- **THEN** no field of it, and no element of its keyword list, contains a `<` followed by a tag name

### Requirement: Padding rows are not records

The export ends with HTML padding rows whose identifier cell is a non-breaking space and whose other
cells are empty. The system SHALL recognise a data row by a numeric identifier, and SHALL treat the
rest as non-data.

#### Scenario: Trailing padding

- **WHEN** the export ends with rows whose identifier cell holds only `&nbsp;`
- **THEN** no record is emitted for them
- **AND** they are counted as skipped non-data rows
