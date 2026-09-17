---
paths:
  - "openspec/**"
  - "tests/test_spec_conformance.py"
---

<!-- Moved out of CLAUDE.md. This is a procedure for writing and archiving spec
     deltas; it only applies when someone is doing that. -->

# Specs and the code that is meant to satisfy them

`openspec validate --strict` checks that a spec is well formed. It does not check
that anything implements it, and the difference has already cost this project
once: `grounded-answering` required bounding "the number of tool calls made in
answering a single question" while the code bounded *model* calls, and the two
only came apart when a model batched several tool calls into one hop.

`tests/test_spec_conformance.py` maps each requirement to the tests that assert
it, and fails when a requirement is neither mapped nor recorded as a gap. **Add
the mapping entry in the same change that adds the requirement**, the way ADRs
are written with the decision rather than collected at the end.

Be clear about what it proves. It catches a requirement nothing claims, and a
claim naming a test that no longer exists. It does **not** catch a test that
claims a requirement and checks the wrong thing — which is exactly what happened
above. What it buys is the requirement's words sitting next to the name of the
test asserting them, where a reader comparing the two can see the mismatch. A
review aid, not a proof. (Which files it reads, and why not recursively, is in
that file's own docstring.)

### A spec delta is the requirement's full new text

A `MODIFIED` block is the **entire requirement as it will now read**, not the
part being changed. Copy the current requirement out of `openspec/specs/` and
edit that copy. Writing out only the paragraphs a change cares about deletes
everything else, and the delta has no baseline to diff against, so it reads as an
addition.

**`openspec archive` refuses a dropped scenario and says nothing about dropped
prose.** That is the whole exposure. `rename-to-scinumbers`'s delta was caught
dropping three scenarios; the same block silently dropped three paragraphs of
requirement text, and nothing would ever have reported it. So after writing a
`MODIFIED` block, diff it against the current requirement mechanically —
scenarios *and* paragraphs.

**Archive each change as it completes.** `MODIFIED` requires its target to be in
`openspec/specs/` already, so changes archive in the order their requirements
landed; letting several pile up turns that into a blocker discovered at the end.
`--skip-specs` is not the way out — it archives the change while promoting
nothing, which is the only reason to archive.
