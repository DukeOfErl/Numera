## Purpose

The curated tier shows BioNumbers' own entries beside harvested ones, at the top of the trust
order, so a reader sees what a reviewed entry looks like and where harvested entries stand.

## ADDED Requirements

### Requirement: Only entries with no sign of doubt are curated

An entry of the BioNumbers corpus SHALL be admitted to the curated tier only if it lies in the
demo's slice (yeast by organism, or the cytoskeleton by property or keyword) and none of these
applies: no value and no two-sided range; no measurement method, or a method that reads as a
calculation, estimate or model; no PubMed reference; bounds the corpus reports may belong to two
quantities; bounds more than a millionfold apart; a one-sided bound; no unit; a unit holding a
character the export garbled; or prose that calls the value uncertain, disputed or a rule of thumb.
An entry the source gives as approximate SHALL be admitted and SHALL say so.

The refusal SHALL hold for every caller that admits entries, not only the command that loads them.

#### Scenario: A fused range
- **WHEN** the corpus reports that an entry's bounds may belong to two quantities
- **THEN** the entry is not curated

#### Scenario: A rule of thumb
- **WHEN** an entry's comments call its value a rule of thumb
- **THEN** the entry is not curated

#### Scenario: An approximate value
- **WHEN** an entry's value is given as approximate and nothing else applies
- **THEN** it is curated and marked approximate

### Requirement: The curated tier is loaded whole and says what it left out

Loading the curated tier SHALL replace it entirely, and SHALL report how many entries were loaded
and how many in the slice were left out for each reason. The corpus SHALL be read at run time and
never committed.

#### Scenario: A reload
- **WHEN** the tier is loaded twice from corpora that differ
- **THEN** it holds exactly the second load's entries
