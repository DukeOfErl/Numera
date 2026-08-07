## Purpose

Scores the validator against a curated reference dataset whose entries already record where each
number came from. It exists to keep two very different questions apart — how much of the literature
we can reach, and how well we judge what we reach — because a single blended accuracy figure hides
which of the two is failing.

## ADDED Requirements

### Requirement: Evaluation corpus is a swappable, external input

The benchmark SHALL treat the reference corpus as a configurable input and SHALL NOT depend on any
particular curated dataset. The corpus SHALL NOT be stored in this repository, and the benchmark
SHALL fail with an explanatory message when no corpus is supplied.

#### Scenario: Corpus supplied at run time
- **WHEN** the benchmark is run with a path to a prepared corpus
- **THEN** it evaluates against that corpus

#### Scenario: No corpus supplied
- **WHEN** the benchmark is run without a corpus
- **THEN** it stops with a message explaining that a corpus must be supplied
- **AND** does not fall back to any bundled data

### Requirement: Reproducible subset definition

The evaluation subset SHALL be defined by recorded selection criteria that can be re-run to yield an
identical set of entries. The definition SHALL consist of automatic criteria plus an explicit list
of manually curated inclusions, and re-running selection over an unchanged corpus SHALL produce the
same entries.

For the cytoskeleton subset the criteria SHALL be:

- **Include** an entry whose *property* field matches a cytoskeletal term (cytoskeleton, microtubule,
  microfilament, actin, tubulin, myosin, kinesin, dynein, dynactin, spectrin, septin, centrosome,
  centriole, FtsZ, MreB, crescentin, ParM, Arp2, formin, cofilin, profilin, gelsolin, tropomyosin,
  filamin, actinin, villin, talin, vinculin, vimentin, keratin, desmin, neurofilament, intermediate
  filament, kinetochore, mitotic spindle, treadmilling, dynamic instability, stress fibre,
  lamellipodium, filopodium), matched on whole-word boundaries.
- **Exclude** any entry mentioning flagella, cilia, axonemes, pili, or fimbriae, as motile and
  adhesive appendages are out of scope for this subset.
- **Exclude** entries matching a cytoskeletal term only in their keyword list and not in the
  property field, because that group was measured to be substantially noisier and less scorable.
- **Include, by explicit curation**, the following entries which match only via keywords but were
  confirmed to be cytoskeletal measurements: `109811`, `111058`, `111478`, `112209`, `114285`,
  `114287`.

#### Scenario: Selection is re-run over an unchanged corpus
- **WHEN** subset selection runs twice over the same corpus
- **THEN** both runs yield an identical set of entry identifiers

#### Scenario: Entry matches only via keywords and is not curated in
- **WHEN** an entry matches a cytoskeletal term only in its keyword list
- **AND** its identifier is not in the curated inclusion list
- **THEN** it is excluded from the subset

#### Scenario: Entry mentions an excluded appendage
- **WHEN** an entry mentions flagella, cilia, axonemes, pili, or fimbriae
- **THEN** it is excluded from the subset regardless of other matches

### Requirement: Scorable entries are identified explicitly

The benchmark SHALL classify an entry as scorable only when it carries a persistent source
identifier, a numeric value or range, and a curator quotation from the source. Entries failing any
of these SHALL be retained and reported, but SHALL NOT contribute to capability figures.

#### Scenario: Entry meets all three conditions
- **WHEN** an entry has an identifier, a numeric value, and a curator quotation
- **THEN** it is classified as scorable

#### Scenario: Entry lacks a curator quotation
- **WHEN** an entry has an identifier and a numeric value but no quotation
- **THEN** it is classified as not scorable
- **AND** it is still counted in coverage reporting

### Requirement: Gold evidence derived from curator annotations

WHERE a scorable entry's curator quotation contains the claimed value, the benchmark SHALL treat
that quotation as the gold evidence span for the entry. WHERE the quotation does not contain the
value, the benchmark SHALL mark the entry as lacking gold evidence rather than inferring one.

#### Scenario: Quotation contains the claimed value
- **WHEN** an entry's curator quotation contains the claimed value
- **THEN** the quotation is recorded as that entry's gold evidence span

#### Scenario: Quotation does not contain the claimed value
- **WHEN** an entry's curator quotation does not contain the claimed value
- **THEN** the entry is marked as lacking gold evidence
- **AND** no gold span is inferred from surrounding text

### Requirement: Coverage and capability reported as separate figures

The benchmark SHALL report coverage — the proportion of subset entries for which a source could be
retrieved and examined — separately from capability — the proportion of attemptable entries judged
correctly. The benchmark SHALL NOT report a single combined accuracy figure.

#### Scenario: Results are reported
- **WHEN** a benchmark run completes
- **THEN** the report states coverage and capability as distinct figures
- **AND** states the denominator used for each

#### Scenario: Combined figure requested
- **WHEN** any output would blend unreachable and misjudged entries into one accuracy number
- **THEN** the benchmark does not emit that figure

### Requirement: Results stratified by failure mode

The benchmark SHALL break results down by the reason entries were not attempted or not judged
correctly, including at minimum: no persistent identifier, no open access, non-article source,
figure-only content, value obtainable only by derivation, and semantic mismatch.

#### Scenario: Report is produced
- **WHEN** a benchmark run completes
- **THEN** counts are given per failure mode
- **AND** the failure modes partition the entries that were not judged correctly

#### Scenario: Subset is truncated or sampled
- **WHEN** a run evaluates only part of the selected subset
- **THEN** the report states how many entries were omitted and why
- **AND** does not present partial results as full-subset results

### Requirement: Verdict agreement measured against gold evidence

For entries with gold evidence, the benchmark SHALL compare both the verdict and the located
evidence span against the gold span, and SHALL report located-evidence agreement separately from
verdict agreement.

#### Scenario: Verdict and span both agree
- **WHEN** the validator returns a supporting verdict
- **AND** its evidence span overlaps the gold span
- **THEN** the entry counts towards both verdict agreement and evidence agreement

#### Scenario: Verdict agrees but span does not
- **WHEN** the validator returns a supporting verdict
- **AND** its evidence span does not overlap the gold span
- **THEN** the entry counts towards verdict agreement only
- **AND** the disagreement is reported
