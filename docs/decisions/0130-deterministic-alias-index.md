# ADR-0130: A deterministic alias index, not long-term agent memory

- **Status:** accepted
- **Date:** 2026-08-26
- **Pull request:** _pending — `feat/ask-agent`_

## Context

People ask about "E. coli"; the corpus stores `Bacteria Escherichia coli`. Across
841 distinct organism strings, resolving what someone typed to what is stored is
knowledge worth keeping, and long-term agent memory is the obvious-looking home
for it — the framework provides a store, and "the agent learns the names" is an
appealing sentence.

## Decision

The mapping is a **deterministic index built from the corpus at load time**, and
inspectable.

Plain case-insensitive substring matching already reaches a genus, a common name
or a group, since each is a substring of the stored value. The one variant it
cannot reach is the abbreviated binomial — `e. coli` is not a substring of
`Bacteria Escherichia coli` — so that is the whole of what the index covers.

## Trade-off accepted

The index over-generates. Its rule takes any capitalized-then-lowercase token
pair, which also catches common-name phrases. Rejecting a pair followed by another
lowercase word removed the clear cases (`African clawed frog` no longer yields
`a. clawed`, dropping 52 of 659 keys), but a few survive where a capitalized genus
follows the phrase — `f. yeast` from `Fission yeast Schizosaccharomyces pombe`.
Tightening further would cost real binomials: rejecting on a following capitalized
word loses `Acanthamoeba polyphaga`, and requiring the pair to be final loses the
79 stored names carrying a suffix, `Peanut Arachis hypogaea L.` among them.

The residual keys are inert — an alias is consulted only when someone types it,
and nobody types `f. yeast` — and because the index is inspectable, a wrong key is
visible rather than silent. Inert noise is preferable to losing a real
abbreviation.

Against agent memory, what is given up is adaptation: the index learns nothing
from use, and a naming variant it does not cover stays uncovered until someone
changes the rule. What is bought is that the mapping is identical for every user,
reproducible, correctable by hand, and visible when wrong — where memory would be
per-user, non-deterministic, and invisible when wrong.
