## ADDED Requirements

### Requirement: A cited entry from the store is shown with its trust tier as stars

Where the corpus is the harvest store, every citation in an answer and every row of the entries
shown with it SHALL carry the entry's trust tier as stars on one scale: five for a curated entry,
then four, three, two and one for the highest reviewer role that approved it — senior scientist,
scientist, student, AI — and zero where no one approved it. The tier SHALL be the one ADR-0990's
rule reads off the store's decisions.

The stars SHALL be drawn by the application from the store, never written by the model, and the
model SHALL NOT be asked to write them. A tier the model writes is a tier it can get wrong, and a
wrong star rating looks exactly like a right one. Where the model writes stars anyway, they SHALL
NOT be taken for the tier.

A disputed entry — one a reviewer objected to, whether or not another approved it — SHALL carry a
caution beside its stars. The stars say who approved it; the caution says that someone did not, and
neither is folded into the other.

Wherever a tier was set by a simulated review, the stars SHALL carry a mark saying so, and what the
mark means SHALL be stated where it is shown. The demo's reviews are models standing in for people,
and a star a reader takes for a person's judgement is a claim the store does not make.

What the scale means SHALL be stated where the stars are shown: which role each count stands for,
what the caution means and what zero means.

An entry from a corpus file carries no tier, and SHALL show no stars — not zero stars, which would
say that someone looked and no one approved.

#### Scenario: An answer cites a curated entry
- **WHEN** an answer cites a curated entry
- **THEN** five stars are shown beside the citation and in its row

#### Scenario: An entry approved by a student and a scientist, and objected to by another student
- **WHEN** an answer cites an entry a student and a scientist approved and another student objected to
- **THEN** three stars are shown, for the scientist
- **AND** a caution is shown beside them

#### Scenario: An entry no one approved
- **WHEN** an answer cites an entry that reviewers objected to and no one approved
- **THEN** zero stars are shown, with a caution

#### Scenario: A tier set by a simulated review
- **WHEN** the review that set an entry's tier was simulated
- **THEN** its stars carry the simulated mark
- **AND** what the mark means is stated where the stars are shown

#### Scenario: The model writes stars
- **WHEN** the model's answer contains star characters beside a citation
- **THEN** the tier shown is still the one read from the store

#### Scenario: The corpus is a file
- **WHEN** the corpus is a corpus file
- **THEN** no stars, caution or simulated mark is shown on any citation or row
