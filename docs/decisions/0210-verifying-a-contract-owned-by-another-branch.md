# ADR-0210: Verifying a contract whose owner is on another branch

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _(not yet opened — branch `feat/corpus-ingestion`)_

## Context

This change's done-criterion is that `bionumbers_ask.corpus.load` accepts its output. That loader is
on `feat/ask-agent`, which is checked out in a different worktree and shares no source tree with this
branch, so it cannot be imported here.

Its failure modes are the reason this matters. Reading the loader's code:

- It raises on the **first** unusable line and returns nothing, so one malformed line costs all
  14,294 entries rather than one.
- `_number` coerces `""` to `None`, but `""` **is not** `None`. An emitted `""` therefore satisfies
  the loader's has-a-value branch and blanks out the measurement of every range-only entry — 4,985
  entries of the real corpus.
- `_keywords` passes a string to `tuple()` when the corpus stores one, and `tuple("abc")` yields one
  entry per character, silently.

None of these is caught by asserting that the required keys are present, which is what a naive
contract test does.

## Decision

Verify in three layers, each covering what the others cannot.

**(a) A contract test in this branch.** The twelve required keys and their accepted JSON types are
written as one literal in `tests/test_corpus_contract.py`, with a comment naming its source
(`bionumbers_ask.corpus.Entry`, `feat/ask-agent`). It ingests the fixture and asserts every emitted
line trap by trap: absent scalars are `null` and never `""`, `keywords` is an array and never a
joined string, `bnid` is a number. It is deliberately the only copy of the contract in this branch.

**(b) A round-trip test that activates on merge.** `pytest.importorskip("bionumbers_ask.corpus")`,
then ingest and call the real `load()`. It skips here and becomes live the moment this lands on `dev`
beside the agent — which is also the moment loader drift would otherwise start going unnoticed. It
was run once with the extracted loader on `PYTHONPATH` to prove it passes when it is not skipped: a
guarded test nobody has ever seen execute is indistinguishable from a broken one.

**(c) A one-off verification by hand during implementation.** Extract the loader into the scratch
directory with `git show feat/ask-agent:src/bionumbers_ask/corpus.py` and load a produced corpus with
it. This touches neither branch nor the other checkout, and the extracted copy is never committed —
the same discipline as fault seeding: work in a copy, leave nothing behind.

Layer (c) was moved from group 8 to group 5, immediately after the writer exists. Every trap above is
a *serialization* decision, so verifying after provenance, reporting and the command would have left
five groups between causing such a bug and observing it, and none of those groups touches the
contract.

Result, recorded in `tasks.md`: 14,294 records written and 14,294 entries loaded, zero rendering as
an empty measurement, zero per-character keyword lists.

## Trade-off accepted

**The literal in (a) can go stale, and nothing here will notice.** If the loader gains a required
field or changes a coercion, this branch's tests keep passing while the real contract has moved. The
mitigation is not technical — it is that the other branch's `corpus.py` carries a docstring saying a
change to `Entry` needs a message to this change, and that (b) goes live at the merge. Between now and
that merge, the protection is a promise between two work packages.

**Layer (c) verifies a snapshot.** The extracted loader is whatever `feat/ask-agent` had at the moment
of extraction, so a "verified by hand" result has a shelf life. It is recorded with what it proved
rather than treated as a standing guarantee.

*Rejected: vendor `corpus.py` into this branch's tests.* Two copies of a contract drift, and the drift
is silent in the one direction that matters — the vendored copy keeps passing while the real loader
has moved on. The literal in (a) has the same weakness but is a third of a page rather than 133 lines,
and it states the contract rather than reimplementing it.

*Rejected: defer verification to the merge.* A port whose acceptance nobody has observed is not
finished, and the merge is the worst moment to discover the output shape is wrong.
