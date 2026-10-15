# ADR-1240: Citations are shown as grey superscripts, and the door says where the rest is

- **Status:** accepted
- **Date:** 2026-10-04
- **Pull request:** _pending — `feat/door-demo-mouse-cells`_

## Context

Answers cite entries in the delimited form `[[nnnnnn]]` (ADR-0410), and both the app
and the door showed that form as it is, in the body text. A sentence like "yeast
volumes between 26–74 μm³ [[100427]] [[100430]] [[103704]]" reads as much bracket as
prose. Yoav asked for the identifiers to stand apart from the text.

He saw three styles drawn on the door's own examples:

- **A:** grey and smaller, double brackets.
- **B:** the same with single brackets.
- **C:** a grey superscript.

He chose C, with a run of identifiers joined by commas.

One cost was visible in the preview. Where a sentence uses an identifier as a noun
("**Computed** from [[100427]] and [[100004]]"), a superscript leaves the sentence
with nothing to point at. He accepted that.

## Decision

**A run of citations is one grey superscript, comma-separated.** A run is one or more
`[[nnnnnn]]` separated by spaces or a comma; words between citations start a new run.
`[[100427]] [[100430]] [[103704]]` is drawn as <sup>100427, 100430, 103704</sup> in
the muted grey, at about 70% size, with no line-height of its own so it does not open
up the line spacing.

**The door says where the full citation is.** Every example ends with "*The app itself
provides full citations", in the same grey. It comes before an example's own notice:
case 3's red "*Charts are an upcoming feature in SciNumbers". The door shows only
identifiers, and a visitor should not take a bare number for the whole reference.

A citation inside a fenced block, such as a chart, is left as written.

**The door first, then the app** (Yoav's order). The app draws answers with
`st.markdown`, so the change there is a separate chore branch.

## Trade-off accepted

The citation form the model writes and the form a reader sees now differ. The parser
and the evaluation still read `[[nnnnnn]]` from the text, and the restyling happens
only where an answer is drawn. Sentences that name an identifier as a noun read
slightly worse. Rewording them is an edit to the examples, not to the style.
