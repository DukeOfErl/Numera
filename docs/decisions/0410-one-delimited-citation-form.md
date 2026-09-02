# ADR-0410: One delimited citation form for answers, and why the parser still tolerates BioNumbers'

- **Status:** accepted
- **Date:** 2026-09-01
- **Pull request:** _pending — feat/scinumbers-citation-form_

## Context

The model was asked to cite as `BNID 100002`, and one parser read that notation in
two different texts: an answer the model wrote, and an entry's prose the source
wrote. Only the first is ours to design.

Reading a notation that marks where an identifier *begins* but not where it *ends*
costs real machinery, and every piece of it was paid for by a defect. A width floor
(`MIN_DIGITS`), because `BNID 104 678` was being read as an entry 104 — a citation
the parser used to miss turned into a wrong one it reported confidently. A run rule,
because `BNIDs 100002 and 100003` was read as one citation and a well-cited answer
scored as having none. A same-number-of-digits continuation, so that
`BNID 100002 and 3 other entries` did not contribute an entry 3.

All of it exists to infer a boundary. None of it is needed for text we control the
format of.

Two further forces. The corpus is BioNumbers today and will not always be, so a
notation naming one database is a notation that has to change; and the identifier is
an integer today, with a widening to strings recorded as possible (ADR-0430) — a
parser whose rules are all about digit counts is a parser that widening would have
to rewrite.

Against that: a reader who knows BioNumbers types `BNID 100002` into their own
question. Sessions are checkpointed and follow-ups inherit the conversation
(`agent-session`), so once that form is in the transcript it stays for the session
and the model answers in it. A delimited-only parser would mark every one of those
well-cited answers unsupported.

## Decision

The model is asked to cite as `[[100002]]`, and `citations.py` parses that with **no
shape rules at all** — no minimum width, no run heuristic, nothing about how many
digits an identifier has. The closing delimiter says where the identifier ends.

`citations()` **also** accepts BioNumbers' notation, by calling `bionumbers.py`
rather than restating it. The two are merged by position, not concatenated, so the
entries table still shows rows in the order the answer cites them.

The prompt interpolates `citations.FORM` instead of restating the form. It restated
it for the project's whole life with nothing tying the two together: the prompt
could have asked for a notation the parser did not read, and the only symptom would
have been every answer reported as uncited.

A bracket group holding no identifier is recorded to the trace, never dropped in
silence — an answer that tried to cite and failed is otherwise indistinguishable
from one that never tried.

A live probe (`tests/test_live_model.py`) confirms a real model actually produces the
form. The previous notation had observation behind it and this one had none;
asserting a form no model had been seen to write would have been a change made on
faith.

## Trade-off accepted

**The source's shape rules stay reachable from the answer path.** Tolerance means
`MIN_DIGITS` and the run rule are still live for answers, so widening the identifier
to a string touches two parsers rather than one. Bought deliberately: the alternative
is a false negative on the exact reader most likely to use the system, and a false
negative marks a good answer unsupported, which is the failure this project exists to
prevent.

**A machine notation is now visible in answers.** `[[100002]]` reads worse to a person
than `BNID 100002`, and it names no database. The entries table beside the answer is
where attribution is made instead, and it says `BNID 100002` (ADR-0420).

**Two notations mean two things to keep working.** The mitigation is that there is one
*implementation* of the source's notation, called from both places and asserted to be
the same function object — the defect being avoided is two independent readings of one
notation, which this project has already had once.
