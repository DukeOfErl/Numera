# ADR-1500: A domain is a scope in the user turn, and its name is on every claim

- **Status:** accepted
- **Date:** 2026-10-07
- **Pull request:** not yet opened — branch `feat/harvest-prototype`, change `add-harvest-prototype`

## Context

Harvest mode (ADR-0950) was built for yeast and the cytoskeleton: seven classes of value read off
BioNumbers' entries, and a list of what is never wanted. The demo now takes papers from four
domains — biology (planarians), biophysics (cytoskeletal mechanics), chemistry about the
cytoskeleton, and the physics of the glass transition. Their reusable numbers differ in kind: a
glass has a transition temperature and no organism; a chemist looks up dissociation constants
and quantum yields; in biophysics a reconstituted actin network is the object measured, which
the biology scope sets aside as "this study's own preparation".

Options: one broad scope naming every class for every domain, which asks a biology paper for
transition temperatures and invites the incubator setting; a separate instruction per domain,
which forks the quoting rule, the claim categories and the conditions four ways; or one
instruction with a per-domain scope.

## Decision

A domain is a `Scope` in `bionumbers.harvest.SCOPES` — wanted classes and unwanted kinds, as data
— and nothing else differs. The scope travels in the user turn, as before, so the cached paper
prefix and the instruction are the same in every domain. `bionumbers harvest --scope NAME` records
it in the run's request, and the scope's name is written to the fingerprint of every paper and
claim (`Fingerprint.scope`): two scopes asked of one paper are two different questions of it, and
a dashboard needs the domain without joining run files. A harvested run from before scopes is read
as `biology`, the scope its classes were.

The instruction gained one sentence that every domain needs: a value that belongs to no organism
is labelled with its material or system.

## Trade-off accepted

The scopes for chemistry and physics are written from a handful of papers, not read off a curated
corpus as the biology one was, so they are guesses about what a chemist or physicist would look up.
The instruction's condition fields remain biological (strain, medium, growth phase); a physics
claim records its own conditions under names the model chooses, which nothing yet normalises.

## Amendment, 2026-10-09: an organism-level scope

The biology scope, read off yeast and the cytoskeleton, returned nothing from eight of ten papers
by the demo's reviewers — zoology, palaeontology, regeneration and cardiac physiology — and the
model said why each time: the numbers were about bodies, fossils or tissues, not cells. A fifth
scope, `organismal`, asks for organism-level sizes, counts, genomes, life-history times,
physiological quantities and proportions, and sets aside phylogenetic support values and numbers
of specimens examined. Nothing else changes; the decision above holds.

## Amendment, 2026-10-09: each scope names its condition fields

The trade-off above — the instruction's condition fields remain biological — did not survive the
first review of the demo database: on a physics entry every field (strain, medium, growth phase)
read "not stated", and the condition that mattered, the glass's preparation or pressure, appeared
nowhere. Each scope now carries its condition fields, and they travel in the user turn with the
classes; the harvest instruction says only "the condition fields the user turn names", and refuses
to build if the question instruction's own list moves. Biology keeps the original eight. Entries
extracted before this carry the biological fields.
