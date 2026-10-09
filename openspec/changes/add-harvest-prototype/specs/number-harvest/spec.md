## Purpose

Harvesting reads chosen research articles ahead of any question and keeps the values each one
establishes that a scientist outside the study would look up, so that questions can later be
answered from a store rather than by searching for papers.

## ADDED Requirements

### Requirement: A harvest starts from chosen articles and asks each for its reusable values

A harvest SHALL start from a list of article identifiers rather than from a search, fetching each
article's full text and recording its metadata and licence as discovery does. Extraction of a
harvested run SHALL ask each article once, with no question, for the values it itself establishes
that are worth reusing, and SHALL keep every other rule of extraction: verbatim quotes checked
mechanically, one retry, the claim categories, the conditions, and a second text per claim.

An article SHALL yield at most twenty entries. A value an article computes itself from other
publications' data SHALL be an entry, under a category of its own; a value it only restates from
other work SHALL NOT.

#### Scenario: A run from a list
- **WHEN** a harvest is started from a list of identifiers
- **THEN** each article is fetched and recorded with its metadata and licence, and an article
  without full text is recorded with the reason, never as an error

#### Scenario: An article with nothing worth reusing
- **WHEN** an article states no value of the wanted kinds
- **THEN** it ends as having nothing to extract, with the model's reason, and costs one call

### Requirement: A harvest asks in one named domain, and the domain is on every entry

A harvest SHALL be asked in one of a fixed set of domains — biology (cells and molecules),
organismal biology, biophysics, chemistry, physics — each stating the classes of value wanted and the kinds not wanted. The domain SHALL
change nothing else about extraction. The statement of a domain SHALL name no unit and no
magnitude. The domain SHALL be recorded with the run and on every article's and entry's record of
what produced it; a harvested run recorded before domains existed SHALL be read as biology.

#### Scenario: A physics harvest
- **WHEN** a harvest is asked in physics
- **THEN** the model is asked for that domain's classes of value, and every entry from the run
  records physics

#### Scenario: A run from before domains
- **WHEN** a harvested run records no domain
- **THEN** it is extracted and recorded as biology

### Requirement: A harvested entry names its quantity, its class and what it belongs to

Each entry SHALL carry three labels written by the model and not quoted: a short general name for
the quantity, one of the domain's classes, and the organism — as the Latin binomial wherever the
article gives one — or, for a value that belongs to no organism, the material or system as the
article names it. The value field SHALL hold no unit.

Where an article reports the same quantity under more than one condition, the name of every value
but the article's control SHALL end with its condition as a scientist would name it — growth
state, genotype or construct, tissue, developmental stage, position, or outside biology the sample
or state — and never as a table's row or column label. The value the article marks as its control
or wild type SHALL carry no condition in its name.

#### Scenario: Two conditions of one quantity
- **WHEN** an article reports a ring spacing for two constructs
- **THEN** the two entries are named by their constructs, not both by the bare quantity

#### Scenario: A glass
- **WHEN** a value belongs to a material rather than an organism
- **THEN** the entry is labelled with the material

### Requirement: A hand-chosen article's licence is the index's where the document is silent

The licence recorded for a harvested article SHALL be the one the literature index states for it,
and the document's own statement only where the index states none. An article whose document
states its licence only in prose SHALL NOT be recorded as unlicensed when the index states one.

#### Scenario: A licence in words only
- **WHEN** an article's document says it is openly licensed without a link, and the index records
  CC BY
- **THEN** the article is recorded as CC BY and its entries may be loaded

### Requirement: Every entry records the model that answered

The record of what produced an article's state and its entries SHALL name the model that the
provider reports answered, beside the model asked for, where the provider reports one; where two
calls were answered by different models, both SHALL be named.

#### Scenario: A routed call
- **WHEN** a call asked of one model is answered by another
- **THEN** the entries record both names
