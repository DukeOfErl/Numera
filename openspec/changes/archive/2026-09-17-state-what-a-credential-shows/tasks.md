# Tasks

No ADR block is allocated for this change, and none is written: nothing here decides anything. The
deltas state behaviour the code already has, and the two places where the code could have been wrong
were checked first — the answers are recorded in group 4 rather than in a decision record.

## 1. The spec deltas

- [x] 1.1 `user-identity`: an ADDED requirement for what the interface states about a credential, with
      a scenario per finding — the renewal stated as given, the renewal that cannot be read stated
      not at all, the fetch's own answer, and the provider's remaining preferred over the figure
      worked out from its cap and usage.
- [x] 1.2 `user-identity`: a MODIFIED block for the enrolment requirement, adding the sentence about
      preserving what could not be read. Copied whole out of `openspec/specs/` and diffed against it
      mechanically afterwards — paragraphs as well as scenarios.
- [x] 1.3 `answer-feedback`: a MODIFIED block for the requirement that governs what a rating names,
      adding the run label. Diffed the same way.

## 2. The tests for what a credential shows

- [x] 2.1 The renewal through `parse`: a payload naming it, and the line stating it. The existing test
      built `Allowance(resets=...)` by hand, so nothing read the payload's key at all.
- [x] 2.2 The negative for it, varying the field the guard reads rather than the outcome: a renewal
      that is `None`, a number, or an object is no renewal, and the line says nothing about one.
- [x] 2.3 A successful `fetch` asserted on its answer, not only on its outgoing request, with all four
      fields distinguishable so a field read off the wrong key shows.
- [x] 2.4 The provider's `remaining` against a fixture where the provider disagrees with itself —
      `limit_remaining` that is not `limit - usage` — and the negative case with that one field gone.

## 3. The two blind tests in the same file

- [x] 3.1 `test_an_empty_key_is_not_asked_about` and `test_an_empty_key_is_not_probed` raised their
      `AssertionError` inside the opener, which `fetch` and `probe` catch along with everything else.
      The opener now records the call and returns a response that would be visible in the result; the
      claim is asserted after the call returns. Say in the docstring why the shape matters, since
      mutation testing cannot flag it: inverting `if not api_key` breaks the positive cases too, so
      the mutant dies for the wrong reason.

## 4. The rating's run, and the operator's clue

- [x] 4.1 A rating's run label against a question's own, driven from the environment both sides read,
      with a label that is neither side's default; and the same with nothing configured.
- [x] 4.2 `accounts.lookup`'s refusal carries the type and the message of what failed, over three
      causes an operator would act on differently.
- [x] 4.3 The clue reaches the operator through the page's own path, on stderr, and the reader's
      sentence is still the one that says nothing about the database.

## 5. Both source questions, answered before writing a line of source

- [x] 5.1 **Does `as_text` prefer the provider's figure in every branch, or only in the one the old
      fixture exercised?** It prefers it wherever it states a "left" figure: `left = remaining`, and
      the subtraction happens only when `remaining` is `None`. No source change. The one branch that
      states no "left" figure at all is the uncapped one, which prints usage and "no cap set"; a
      `limit_remaining` arriving with no `limit` beside it is therefore not shown, which is an
      omission and not a derivation. Left alone.
- [x] 5.2 **Can `feedback._record` emit a null run label on any real path?** No. It reads
      `SCINUMBERS_RUN`, strips it, and falls back to `"dev"`, which is character for character what
      `Config.from_env` does for the question. The null the mutation run produced needs the fallback
      removed: an empty label reaches `trail_store` as `NULL`, and the row then joins to no run. Test
      only, no source change.

## 6. Finishing

- [x] 6.1 Map every new and modified requirement in `tests/test_spec_conformance.py`.
- [x] 6.2 `ruff check` and `ruff format`, then the suite once.
- [x] 6.3 Seed a defect per new test into a copy of the source and check that exactly the right test
      fails — including the two repaired blind tests against a copy with the empty-key guard removed,
      which is the whole reason they were rewritten.
