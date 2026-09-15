---
paths:
  - "tests/**"
  - "src/**/*.py"
---

<!-- Moved out of CLAUDE.md, which targets under 200 lines. Scoped to `paths:`
     so it loads when Claude touches tests or source, not on every session.
     Source is included because fault seeding and mutation testing are decided
     while changing a module, not while editing its tests. -->

# Running the tests

A repeated-run harness -- fault seeding, mutation testing -- should exclude the `slow` marker as well, and must write the **whole** expression: `pytest -m "not network and not corpus and not slow"`. A second `-m` replaces `addopts` rather than ANDing with it, so `-m "not slow"` alone re-selects `network` and `corpus` and the run gets *slower* -- silently. 63s becomes 34s written correctly.

`pytest` is offline by default and runs on the six-entry fixture: `addopts = "-m 'not network and not corpus' -p no:deepeval"` deselects both markers, so a green run may never have executed the tests that hit a real service or the ones that check a marker can fire against a real corpus. Run those explicitly with `pytest -m network` and `SCINUMBERS_CORPUS=... pytest -m corpus`.

`-p no:deepeval` is there because the `eval` extra installs DeepEval, which registers a pytest plugin that prints a teardown line after every run — including runs that touch none of its code. Collection is unaffected; it is the output that moved, and "the suite output is unchanged" is not checkable if it depends on which extras a developer installed. Harmless where DeepEval is absent, since `-p no:<name>` for an uninstalled plugin is not an error — which matters because this file is shared by all three work packages. Group 6 of `add-answer-evaluation` may want DeepEval's own pytest integration back; that means overriding `addopts` in that run, and the whole expression has to be written out, exactly as with `-m`.

# Testing the tests

Two techniques, both scoped by consequence: spend the effort where a silent bug would be *unfalsifiable to the user* — parsers, retrieval, provenance — and not on drivers, rendering or config, where a bug announces itself the moment someone looks.

**Fault seeding** is the default, and the user-level conventions cover it: seed one realistic defect into a *copy* of the source and check that exactly the right test fails.

**A negative case has to differ from the positive one in the dimension the rule actually reads.** This is narrower than "test both directions", and it is what three blind tests in this project had in common — each read correctly and proved nothing, and each was found by seeding rather than by review. `_is_out_of_credit` checks `status_code == 402`; its negatives were `RuntimeError` and `TimeoutError`, which carry no status at all, so the mutant `status_code is not None` — under which every 429 and 502 would permanently close the run — passed all 905 tests. The negatives had to be real `APIStatusError`s at 429, 502 and 401. Before writing a negative case, name the dimension the predicate reads and check the case varies *that*, not merely the outcome.

**No coverage claim before the mutant dies.** Do not write "both directions are pinned" in an ADR, a task list or a commit message until a seeded defect has actually failed the test you are crediting. ADR-0600 asserted it and was wrong, and the claim then stood in the record as a reason not to look again — which is worse than saying nothing, because a false all-clear retires the suspicion that would have found the gap. Write the claim after the seeding, and name the mutant that died.

**Mutation testing** is the automated complement, and finds what seeding structurally cannot — code no test can distinguish. Run it at the end of a task, over the module just touched, via the **`mutation-test-module`** skill, which carries the recipe and this project's four setup gotchas. Not over the whole package (2,000+ mutants, hours) and never as a CI gate.

Its yield decays, and that is expected rather than a failure: a module's first run finds real gaps, later runs on settled code return mostly equivalent mutants. Once two or three consecutive runs turn up nothing but string-sentinel and default-argument survivors, stop running it on that area and reach for it again only when the code changes substantially. It is a tool for new and reworked code, not a standing gate.

**Yield decays per instrument, not absolutely, and that distinction has already been paid for.** `cleaning.py` was reviewed by reading seven times, with findings each time and no downward trend: 9, 11, 6, 5, 5, 5, 7. The sixth pass caught a defect the fifth pass had *introduced*, and the seventh — after mutation testing had run over the same module — still found a HIGH. Reading the same code again is the instrument with the fastest decay; a lens it cannot use (mutation testing, a scoped adversarial review, a question about a second caller) resets the yield. So "the last pass found little" is evidence about the instrument, not about the code, and the move is to switch lenses rather than to conclude the module is clean.
