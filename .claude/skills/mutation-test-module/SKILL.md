---
name: mutation-test-module
description: Run mutmut over one module to find code no test can distinguish. Use at the end of a task, on parsers, retrieval and provenance code — the places where a wrong answer looks right. Not for drivers, rendering or config.
allowed-tools: Bash
---

# Mutation-test one module

Mutmut rewrites every function into many variants and reports which survived the test suite. A
survivor is code no test can tell apart from a broken version of itself. This complements fault
seeding, it does not replace it: seeding checks whether the *right* test catches a mistake a person
would plausibly make, and every seed encodes a belief you already hold. Mutation testing finds the
things you had no belief about.

## When to run it, and when to stop

Run it **at the end of a task, over the module just touched**, while the code is still in your head.
Never over the whole package — that is 2,000+ mutants and hours — and never as a CI gate.

Scope by consequence. Worth it on `citations.py`, `repository.py`, `units.py`, `entries_table.py`
and anything else where a silent bug produces an answer that *looks* correct. Skip drivers,
rendering and config, where a bug announces itself the moment someone looks.

**Expect the yield to decay, and act on it.** A module's first run finds real gaps; later runs on
settled code mostly return equivalent mutants. Once two or three consecutive module runs produce
nothing but string-sentinel and default-argument survivors, stop running it on that area — the tests
there are doing their job, and further triage is cost without return. Reach for it again when the
module changes substantially, not on a schedule.

## Running it

Mutmut is not in `pyproject.toml` — install it into the venv when needed:

```bash
uv pip install mutmut          # needs network; sandbox blocks PyPI
```

Work in a throwaway copy so the repo is never touched:

```bash
REPO="$PWD"; W="$TMPDIR/mut"; rm -rf "$W"; mkdir -p "$W"
# Everything the suite reads, not only source and tests: a conformance test walks
# openspec/, a driver test asserts against README.md, and one imports streamlit_app.py.
cp -r "$REPO/src" "$REPO/tests" "$REPO/openspec" "$REPO/docs" \
      "$REPO/pyproject.toml" "$REPO/README.md" "$REPO/streamlit_app.py" "$W/"
```

Append to the copy's `pyproject.toml`, and add `src` to the pytest path:

```toml
# pythonpath must become ["src", "tests"] — see gotcha 3
[tool.mutmut]
source_paths = ["src/numera_ask"]
also_copy = ["tests/", "openspec/", "docs/", "pyproject.toml", "README.md", "streamlit_app.py"]
pytest_add_cli_args_test_selection = ["tests/"]
pytest_add_cli_args = ["--deselect", "tests/test_repository.py::test_the_repository_exposes_no_way_to_change_the_corpus"]
```

Then run, filtered to one module:

```bash
cd "$W" && "$REPO/.venv/bin/mutmut" run 'numera_ask.citations*'
"$REPO/.venv/bin/mutmut" results | grep survived      # the run log uses 🎉/🙁; results says "survived"
"$REPO/.venv/bin/mutmut" show <mutant-name>           # the diff
```

**Grep `results` for the word, not the emoji.** The progress log prints 🎉/🙁 per mutant;
`results` prints `name: survived`. A `grep 🙁 results` returns nothing and reads as a clean
run — a false all-clear from a harness, which is the one failure mode worth engineering
against.

One module is about four minutes.

## Narrow what each mutant runs — hard

Every mutant pays for the whole suite, so the suite's slow tail is multiplied by the
mutant count. Here five subprocess-spawning tests are **30 per cent of the runtime**, and
nothing a parser mutant changes can reach a process boundary. Unlike fault seeding,
narrowing costs mutation testing no information: it does not report entanglement as a
finding, and mutmut already tracks which tests cover which mutants.

```toml
pytest_add_cli_args = [
    "-m", "not network and not corpus and not slow",
    # ... the deselects above
]
```

**A second `-m` replaces `addopts`, it does not AND with it.** `-m "not slow"` alone
re-selects the `network` and `corpus` markers that `addopts` was excluding — so the run
makes real API calls, needs a corpus, and gets *slower*. Measured here: 63s default,
1m41s with `-m "not slow"`, 34s with the full expression. The failure is silent; it
looks like the exclusion simply did not help.

## Five things that break first

1. **`source_paths`, not `paths_to_mutate`.** The latter is deprecated in 3.7.0. Published docs and
   search results still say otherwise — check the installed source, not the web.
2. **Deselect `tests/test_repository.py::test_the_repository_exposes_no_way_to_change_the_corpus`.**
   Mutmut adds ~169 variant attributes to the class (`xǁCorpusRepositoryǁ__init____mutmut_1`), that
   test asserts the public surface is exactly four names, the baseline fails, and mutmut aborts. Any
   introspection test needs the same treatment.
3. **Any test that reads source text must be deselected — not just introspection tests.**
   Mutmut's rewritten module holds *every* mutant simultaneously (one variant function per
   mutant), and its operators include upper-casing string literals. So a test that greps the
   source sees text no single mutant produces: a guard asserting `"BNID"` appears in no module
   but one fails because mutmut wrote `'bnid'` as `'BNID'` somewhere. This is gotcha 2
   generalised, and it aborts the stats phase rather than one mutant, so the whole run dies.
   In this repo that means:

   ```toml
   pytest_add_cli_args = [
       "--deselect", "tests/test_repository.py::test_the_repository_exposes_no_way_to_change_the_corpus",
       "--deselect", "tests/test_bionumbers_notation.py::test_the_source_marker_appears_in_no_other_module",
       "--ignore", "tests/test_text_reaches_the_page_escaped.py",
       "--ignore", "tests/test_driver_independence.py",
   ]
   ```

   The tell is a baseline failure whose message quotes source text, or an `AssertionError`
   naming a line number far past the end of the real file (`web.py:8091`).

4. **Mutate the whole package, and set `pythonpath = ["src", "tests"]`.** With a `src/` layout and an
   editable install, mutating a single file leaves an incomplete namespace package that loses to the
   real one, and the tests silently run against unmutated source. Mutmut catches this and says *"no
   test covers any mutant"* rather than reporting a fake score — if you see that, this is why.

   Note the copy already has a `pythonpath` line further down its `[tool.pytest.ini_options]`
   block. Inserting a second one does not merge — the later wins, so an insert at the top of
   the block is silently discarded. Edit the existing line.

5. **Deselect anything that asks git about its own working tree.** The copy is not a
   repository, so `bionumbers_ingest.guard.committable_repo_for` returns `None` — "not a
   repository" — and the refusal it exists to make never fires. That is the guard behaving
   correctly, and it fails the baseline, which aborts the run before a single mutant is tried:

   ```toml
   "--deselect", "tests/test_evaluation.py::test_a_results_file_git_would_track_is_refused_before_it_is_written",
   ```

   The tell is a baseline failure in a test whose name mentions git, tracking or committing.
   Same family as gotchas 2 and 3: a test that reads its own environment rather than its
   inputs cannot survive being moved.

## Reading the results

Most survivors are noise. Recognise these and move on:

- `"" → "XXXX"` sentinel defaults — the sentinel matches no pattern, so behaviour is unchanged
- `setdefault(k, None) → setdefault(k,)` — `None` *is* the default
- trace-record event names and kwargs — the trail's content is unasserted by design
- default-argument values (`limit: int = 20 → 21`)

Worth looking at — but read the next section before writing any test for one of these:

- **inverted conditions that survive** (`in` → `not in`) — an untested path, always
- **`continue` → `break`** and similar control-flow flips — these change how much work is skipped
- **boundary flips** (`<` → `<=`, `> N` → `>= N`) on a constant that exists to draw a line
- **a whole clause neutralised** (`x |= y` → `x = y`, `found = repo.get(b)` → `found = None`)

An *equivalent mutant* — one that provably cannot change any result — is not always noise. Sometimes
it localises a redundant branch. Keep the branch if it states intent worth stating, but **annotate it
as redundant**, or the next reader re-derives what you just learned.

## Before killing a survivor: what says the current behaviour is right?

This is the step the technique invites you to skip, and skipping it is worse than not running the
tool at all. A survivor tells you a test cannot distinguish this code from other code. It does **not**
tell you which of the two is correct. Write a test that simply asserts what the code does today and
you have pinned an implementation accident as a requirement — with a passing test and a better
mutation score to make it look like progress, and a bug now defended by the suite.

The tell is mechanical: **if you got the expected value by running the code, you do not have an
oracle.** A test whose assertion came from observed output pins behaviour. A test whose assertion
came from a requirement pins the requirement.

This project has a real oracle — `openspec/specs/`, deliberately implementation-agnostic. Use it.
For each survivor worth acting on, place it in one of three buckets:

- **The spec states this behaviour.** Write the test, and say in its docstring which requirement it
  holds. This is the good case.
- **The spec is silent, and it should not be.** The survivor has found a missing requirement, not a
  missing test. Write the spec delta first — then the test tests something. If you cannot tell what
  the requirement ought to be, **stop and ask**; do not settle it by reading the code.
- **The spec is silent, and rightly so — this is tuning, not contract.** Leave the survivor alive
  and say so, in the nearest test's docstring. Not every mutant should be killed, and a knowingly
  accepted survivor is a decision; an un-triaged one is an oversight.

A worked example from this repo, all three buckets from one run:

| Survivor | Bucket | What was done |
|---|---|---|
| `continue` to `break` in the citation parser | spec states it — a cited answer must not be reported as uncited | test written, requirement named |
| keyword match invertible to `not in` | spec was silent and should not have been | requirement added to `corpus-query`, then tested |
| `MIN_DIGITS` boundary widened | tuning: no spec sets the floor, and the corpus has no four-digit id | **survivor left alive**, and the test now asserts the requirement (a spaced digit group contributes nothing) rather than the number |

The third is the one to learn from. The first attempt asserted the exact boundary, which pinned a
constant chosen empirically as though it were required — and in doing so guaranteed that a four-digit
citation is accepted, which nothing wants. Chasing the mutation score would have kept that test.

## A class of gap only this tool finds: the unasserted mapping

A contract test that checks *which keys exist and what types they hold* is not checking that each key
carries the value of its own column — and when the contract permits `null`, the two are miles apart.

Worked example from `add-corpus-ingestion`. The record has twelve contract keys, ten of which accept
`null`. Mutation testing blanked eight pass-through fields — `property`, `organism`, `reference`,
`reference_pubmed_id`, `primary_source`, `primary_source_pubmed_id`, `measurement_method`,
`entered_by` — and **all 205 tests still passed**, including the contract test built specifically to
guard those keys. A corpus with every text field empty satisfies "the keys are present with an
accepted type" completely: it loads without error and answers questions with no organism and no
citation.

Neither of the other instruments could reach it. Coverage was full — the lines ran. Fault seeding
perturbs code a test already reaches, and no test reached the mapping. Only rewriting the assignment
and finding that nothing objected exposed it.

**So: whenever a record is built by assigning many fields from a source, expect this gap and look for
it.** The fix is a test per field asserting the value arrives, driven from a row where every column
holds a distinguishable value — and the spec requirement that says the mapping is required, not just
the key set.

## Two rules for the harness itself

- **Never truncate silently.** A `tail -N` on the survivor list caps the count without saying so, and
  the capped number then gets reported as a total. Collect in full; truncate at display.
- **Verify the fix.** After adding tests, re-run and diff the survivor list *by name*, not by count —
  new code adds new mutants, so the count can rise while every targeted mutant died.
