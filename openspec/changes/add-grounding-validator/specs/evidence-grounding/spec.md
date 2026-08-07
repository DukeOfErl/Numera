## Purpose

Decides whether a retrieved document actually supports a claimed quantity, and returns the evidence
that justifies the decision. This is the primitive on which trust rankings, human review, and
contradiction detection all depend: a verdict without a citable span is an opinion, not a
verification.

## ADDED Requirements

### Requirement: Graded verdict vocabulary

The system SHALL classify every check into exactly one verdict from the closed set `EXACT`,
`EQUIVALENT`, `DERIVED`, `CONTRADICTED`, `NOT_FOUND`, `UNVERIFIABLE`. The system SHALL NOT return a
bare boolean or an unlabelled score in place of a verdict.

#### Scenario: Value stated verbatim
- **WHEN** the document states the claimed value with the claimed unit
- **AND** the mention describes the claimed quantity
- **THEN** the verdict is `EXACT`

#### Scenario: Value stated in a different but compatible unit
- **WHEN** the document states a value equal to the claim after unit conversion or permitted rounding
- **THEN** the verdict is `EQUIVALENT`

#### Scenario: Value obtainable only by computation
- **WHEN** the claimed value does not appear in the document
- **AND** it follows arithmetically from values that do appear
- **THEN** the verdict is `DERIVED`
- **AND** the evidence identifies the spans the computation used

### Requirement: Unverifiable and unsupported are distinct verdicts

The system SHALL report `UNVERIFIABLE` when no examinable text was obtained, and `NOT_FOUND` only
when examinable text was obtained and searched without finding support. The system SHALL NOT report
one in place of the other, and SHALL NOT aggregate them into a single category in any output.

#### Scenario: No accessible source
- **WHEN** source retrieval reported a typed unavailability reason
- **THEN** the verdict is `UNVERIFIABLE`
- **AND** the retrieval reason is carried through into the result

#### Scenario: Source examined without finding the value
- **WHEN** full text was retrieved and searched
- **AND** no mention supports the claimed quantity
- **THEN** the verdict is `NOT_FOUND`

#### Scenario: Claim depends on figure-only content
- **WHEN** the claimed value is present in the document only within a figure image
- **THEN** the verdict is `UNVERIFIABLE`
- **AND** the result records that the content was not machine-readable

### Requirement: Every supporting verdict carries citable evidence

Any verdict other than `NOT_FOUND` and `UNVERIFIABLE` SHALL include at least one evidence span
giving the quoted source text and its location reference. The system SHALL NOT return a supporting
verdict whose evidence cannot be located in the retrieved document.

#### Scenario: Supporting verdict returned
- **WHEN** the verdict is `EXACT`, `EQUIVALENT`, `DERIVED`, or `CONTRADICTED`
- **THEN** the result includes at least one evidence span with quoted text and a location reference

#### Scenario: Evidence span cannot be located in the document
- **WHEN** a proposed evidence span does not correspond to text present in the retrieved document
- **THEN** the system rejects that span
- **AND** does not report it as evidence

### Requirement: Unit-aware numeric comparison

The system SHALL compare a claimed value against a candidate mention only after normalising both to
a common unit. Values whose units are dimensionally incompatible SHALL NOT be treated as matching,
regardless of numeric equality.

#### Scenario: Same quantity expressed in a different unit
- **WHEN** the claim is `1.5 µm` and the document states `1500 nm`
- **THEN** the values are treated as matching

#### Scenario: Numerically equal but dimensionally incompatible
- **WHEN** the claim is `2.0 µm` and the document states `2.0 s`
- **THEN** the values are not treated as matching

#### Scenario: Dimensionless claim
- **WHEN** the claimed quantity has no unit
- **THEN** comparison proceeds on the numeric value alone

### Requirement: Numeric notation variants are recognised

The system SHALL recognise the notation forms used to express quantities in scientific text, and
SHALL NOT depend on a single canonical spelling. At minimum it SHALL handle both Unicode encodings
of the micro sign, ranges expressed with a hyphen, an en or em dash, or the word "to", uncertainty
expressed as `±`, `+-`, or `+/-`, negative values including the Unicode minus sign, and scientific
notation in both exponent-letter and times-power-of-ten forms.

#### Scenario: Micrometre written with either micro sign
- **WHEN** a quantity is written with either the Greek small letter mu or the micro sign
- **THEN** both are recognised as the same unit

#### Scenario: Range written in any supported form
- **WHEN** a range is written as `0.44-1.79`, `1–2`, or `1.94 to 2.72`
- **THEN** each is parsed as a range with the same low and high bounds it denotes

#### Scenario: Uncertainty expressed as a symmetric interval
- **WHEN** a quantity is written as a value followed by `±`, `+-`, or `+/-` and a magnitude
- **THEN** it is interpreted as the interval from value minus that magnitude to value plus it

#### Scenario: Exponent sign is not mistaken for a range separator
- **WHEN** a value is written in scientific notation with a negative exponent, such as `1.5e-3`
- **THEN** it is parsed as a single value
- **AND** the exponent's sign is not treated as a range separator

#### Scenario: Negative value with a Unicode minus sign
- **WHEN** a value is written with the Unicode minus sign rather than a hyphen-minus
- **THEN** it is parsed as a negative value

### Requirement: Declared tolerance for rounding and reporting differences

The system SHALL treat values as matching when they agree within a declared relative tolerance, and
SHALL report the tolerance applied alongside the verdict. The tolerance SHALL be configurable and
SHALL NOT vary silently between runs.

#### Scenario: Value differs only by rounding
- **WHEN** the claim is `2.0 × 10⁶` and the document states `1.95 × 10⁶`
- **AND** the difference falls within the declared tolerance
- **THEN** the values are treated as matching
- **AND** the applied tolerance is reported

#### Scenario: Value differs beyond tolerance
- **WHEN** the difference between claim and mention exceeds the declared tolerance
- **THEN** the values are not treated as matching

### Requirement: Range and point value comparison

The system SHALL define matching between ranges and point values explicitly. A claimed point value
SHALL match a stated range when it falls within that range; a claimed range SHALL match a stated
range when the two overlap; and the system SHALL record which relation was applied.

#### Scenario: Claimed point value falls inside a stated range
- **WHEN** the claim is `1.05 µm` and the document states `1.0 to 1.1 µm`
- **THEN** the values are treated as matching
- **AND** the result records that a containment relation was applied

#### Scenario: Claimed range overlaps a stated range
- **WHEN** the claim is `5 to 10 µm` and the document states `8 to 12 µm`
- **THEN** the values are treated as matching
- **AND** the result records that an overlap relation was applied

### Requirement: Numeric agreement alone is insufficient

The system SHALL confirm that a numerically matching mention describes the same quantity as the
claim, including the same measured property, organism, and stated conditions, before returning a
supporting verdict. A numeric match that fails this confirmation SHALL NOT be reported as support.

#### Scenario: Same number describes a different property
- **WHEN** the document contains the claimed value
- **AND** the mention describes a different measured property
- **THEN** the mention is not accepted as support

#### Scenario: Same property measured in a different organism
- **WHEN** the document contains the claimed value for a different organism than the claim states
- **THEN** the mention is not accepted as support

#### Scenario: Multiple numerically matching mentions
- **WHEN** more than one mention matches the claimed value numerically
- **THEN** the system evaluates each mention
- **AND** returns as evidence only those describing the claimed quantity

### Requirement: Contradiction is reported, not discarded

WHEN the document states the claimed quantity with a value that falls outside the declared
tolerance, the system SHALL return `CONTRADICTED` and SHALL report both the claimed value and the
value found in the source.

#### Scenario: Source states a different value for the same quantity
- **WHEN** a mention describes the claimed quantity
- **AND** its value differs from the claim beyond the declared tolerance
- **THEN** the verdict is `CONTRADICTED`
- **AND** the result reports both values with the supporting evidence span

### Requirement: Adjudication basis is recorded

The system SHALL record how each verdict was reached, distinguishing decisions made by
deterministic comparison from those requiring a language model, and identifying the model where one
was used. Results SHALL remain auditable after the fact.

#### Scenario: Verdict reached deterministically
- **WHEN** a verdict follows from numeric and unit comparison alone
- **THEN** the result records that the basis was deterministic

#### Scenario: Verdict required semantic judgement
- **WHEN** a verdict depended on judging whether a mention describes the claimed quantity
- **THEN** the result records that a model was used
- **AND** identifies the model
