# value-extraction Specification

## Purpose
From one research article to zero or more claims for the asked property — each a value with a
verbatim quote and location, its conditions and its method with their own provenance — every quote
mechanically verified, under a spend ceiling, with "the paper states nothing extractable" kept
distinct from "the paper could not be read".
## Requirements
### Requirement: A claim is a value the paper measured, quoted verbatim, with a location

Extraction SHALL read one article and produce zero or more claims. Each claim SHALL carry: the value
or range as the paper states it, with its unit; the property in the paper's own words; a verbatim
quote containing the value; the quote's location as a section path and a container (a paragraph, a
table cell with its row and column headers, or a caption); and a kind — a single measurement, a
measurement with stated uncertainty, or a range whose endpoints belong to different conditions.

Only a value the paper **measured**, **derived from its own measurements**, or **computed itself from
other publications' data** SHALL be a claim, and the last SHALL be labelled as such so it is never
read as the paper's own measurement. A
value cited from other work, a value used as a parameter or assumption, and a value in a table that
compiles the literature SHALL NOT be claims for this paper; they SHALL be recorded as rejected
candidates with their category, because the review task draws its second texts from them. A derived
value SHALL be labelled derived and SHALL carry the quoted inputs it was derived from.

A bibliographic citation marker attached to the clause holding a number is decisive evidence that the
value is cited, and outranks any verb in the sentence.

#### Scenario: A measured value in a results table
- **WHEN** the article's results table states the asked property under a named condition
- **THEN** one claim is produced per table row, each quoting its cell with the row and column headers as its location

#### Scenario: A value cited from prior work
- **WHEN** a sentence states the asked property with a bibliographic citation marker on the clause holding the number
- **THEN** no claim is produced from it, and it is recorded as a rejected candidate of kind cited

#### Scenario: The same value restated at lower precision
- **WHEN** the article states one measurement in a table and restates it in prose at lower precision
- **THEN** one claim is produced, quoting the most precise statement, and the restatements are recorded as further occurrences of that claim

#### Scenario: A range spanning conditions
- **WHEN** prose states a range whose endpoints are the extremes of different conditions in the paper
- **THEN** the claim is of kind range-over-conditions and names the condition at each endpoint, and is never recorded as a single measurement with uncertainty

#### Scenario: A derived value
- **WHEN** the article computes a value for the asked property from its own measurements
- **THEN** the claim is labelled derived and carries the quoted inputs

#### Scenario: A value computed from published data
- **WHEN** the article computes a value itself from other publications' data
- **THEN** the claim is kept, labelled as derived from published data, and carries the quoted inputs

### Requirement: Conditions and method are quoted, and each says where it came from

For each claim, extraction SHALL record the conditions of measurement — organism, strain or
genotype, medium or carbon source, temperature, growth phase or rate, culture mode, normalisation
basis — and the measurement method, each as a verbatim quote from the article where the article
states it. Each such field SHALL carry one provenance state: stated beside the value; stated in the
methods section; stated only by reference to another publication; stated only in supplementary
material; or not stated. A field SHALL NOT be filled from anything other than this article's text,
and SHALL NOT be filled from general knowledge.

#### Scenario: Temperature stated only in Methods
- **WHEN** the article's methods section states the culture temperature and no value-bearing sentence does
- **THEN** the temperature field quotes the methods sentence and its state is "from methods"

#### Scenario: Culture conditions offloaded to a cited paper
- **WHEN** the article says its culture conditions were described previously and cites another work
- **THEN** the medium and temperature fields carry the state "by reference", with the cited reference, and no value is invented for them

#### Scenario: A condition the article never states
- **WHEN** the article states nothing about a condition field anywhere in its text
- **THEN** that field's state is "not stated" and its quote is empty

#### Scenario: A table only in supplementary material
- **WHEN** the article refers to values or conditions as being in supplementary tables and its text does not state them
- **THEN** the affected fields carry the state "supplementary only", and the supplementary material is not read

### Requirement: Every quote is verified against the article before anything is kept

Every quote extraction produces — value, condition, method, input and occurrence quotes alike —
SHALL be checked mechanically for verbatim presence in the article's text. The check SHALL tolerate
only whitespace, the folding of typographic variants of dashes, quotes, spaces and the micro sign,
and the removal of inline markup; it SHALL NOT excuse a paraphrase, a changed digit or a changed
unit. A quote that fails the check SHALL be returned to the model once with the failure named; a
quote that fails a second time SHALL cause its claim to be dropped and recorded as unverifiable. No
claim SHALL reach the record or a reviewer with an unverified quote.

The checker SHALL have a recorded canary: a one-digit change to a real quote fails, both in plain
prose and where the source text carries inline markup.

#### Scenario: A quote is verbatim
- **WHEN** a produced quote is found in the article's text after folding
- **THEN** the claim proceeds

#### Scenario: A quote differs by one digit
- **WHEN** a produced quote differs from the article's text by a single digit
- **THEN** the check fails and the model is asked once to correct it

#### Scenario: A quote fails twice
- **WHEN** a quote fails the check after the one correction
- **THEN** its claim is dropped and recorded as unverifiable, and no other claim is affected

### Requirement: Each article ends in exactly one named state

Extraction over one article SHALL end in exactly one of: claims found; nothing to extract (the
article was read and states no measured value for the property); not a research article; unreadable
(no full text, per discovery); ceiling reached (the per-article spend ceiling stopped work); or
failed (a service error the run could not recover from). The state SHALL be recorded with the
article. Nothing to extract and unreadable SHALL never share a state: one is a fact about the paper,
the other a fact about access.

#### Scenario: An article matched by search that states no value
- **WHEN** an article is read in full and its text states the asked property only as a figure or not at all
- **THEN** its state is "nothing to extract", and the reason given by the model is recorded

#### Scenario: An article with no full text
- **WHEN** discovery recorded that no full text could be obtained
- **THEN** the article's state is "unreadable" and extraction is not attempted

#### Scenario: Claims found
- **WHEN** at least one claim passes verification
- **THEN** the article's state is "claims found", with the count

### Requirement: Spend is bounded per article and per run, and reported

Extraction SHALL spend no more than a configurable ceiling per article, defaulting to two US
dollars, and no more than a configurable budget per run. Before each model call, the projected cost
of that call SHALL be estimated from what the provider will be sent, and the call SHALL NOT be made
if it would cross either bound. Actual spend SHALL be taken from what the provider reports and
recorded per article and per run. An article stopped by the ceiling SHALL end in the state "ceiling
reached" with what had been established so far discarded rather than half-kept.

Repeated reads of the same article within one extraction SHALL be arranged so the provider can
serve the article text from its cache, and cache reads SHALL be counted at the provider's cached
rate.

#### Scenario: A call would cross the per-article ceiling
- **WHEN** the projected cost of the next call would take the article past its ceiling
- **THEN** the call is not made, the article ends in "ceiling reached", and no partial claim is kept

#### Scenario: The run budget is exhausted
- **WHEN** the projected cost of the next call would take the run past its budget
- **THEN** no further article is started, and the run records how many articles were left unread

#### Scenario: Spend is recorded
- **WHEN** an article's extraction completes in any state
- **THEN** the provider-reported input, cached-input and output tokens and the derived cost are recorded for it

### Requirement: The model answers from the article, not from what it knows

The extraction instruction SHALL direct the model to use only the article's text, SHALL state that
"nothing to extract" is a correct answer and not a failure, and SHALL NOT supply the model with an
expected value, an expected unit, or a canonical figure for the property. The fact that a famous
value displaces a paper's specific one at high confidence is the recorded failure mode (ADR-0040,
Finding 3), and the instruction is the only place it can be countered.

#### Scenario: A famous property with a paper-specific value
- **WHEN** the article states a value for a property whose textbook figure differs
- **THEN** the claim quotes the article's value, and a claim carrying the textbook figure is not produced because no quote for it exists in the article

#### Scenario: No unit is supplied
- **WHEN** an extraction is requested
- **THEN** the instruction names the property and organism and no unit or expected value

### Requirement: What produced a claim is recorded with it

Every claim, and every article state, SHALL carry the identity of the model, a fingerprint of the
instruction text, the article identifier and the run identifier that produced it, so that items
reviewed later can be grouped by what generated them and never compared across generators
unknowingly.

#### Scenario: A claim is written
- **WHEN** a verified claim is recorded
- **THEN** it carries the model identity, the instruction fingerprint, the article identifier and the run identifier

