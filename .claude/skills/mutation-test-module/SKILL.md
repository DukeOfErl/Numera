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
cp -r "$REPO/src" "$REPO/tests" "$REPO/pyproject.toml" "$W/"
```

Append to the copy's `pyproject.toml`, and add `src` to the pytest path:

```toml
# pythonpath must become ["src", "tests"] — see gotcha 3
[tool.mutmut]
source_paths = ["src/bionumbers_ask"]
also_copy = ["tests/", "pyproject.toml"]
pytest_add_cli_args_test_selection = ["tests/"]
pytest_add_cli_args = ["--deselect", "tests/test_repository.py::test_the_repository_exposes_no_way_to_change_the_corpus"]
```

Then run, filtered to one module:

```bash
cd "$W" && "$REPO/.venv/bin/mutmut" run 'bionumbers_ask.citations*'
"$REPO/.venv/bin/mutmut" results                      # 🎉 killed, 🙁 survived
"$REPO/.venv/bin/mutmut" show <mutant-name>           # the diff
```

One module is about four minutes.

## Three things that break first

1. **`source_paths`, not `paths_to_mutate`.** The latter is deprecated in 3.7.0. Published docs and
   search results still say otherwise — check the installed source, not the web.
2. **Deselect `tests/test_repository.py::test_the_repository_exposes_no_way_to_change_the_corpus`.**
   Mutmut adds ~169 variant attributes to the class (`xǁCorpusRepositoryǁ__init____mutmut_1`), that
   test asserts the public surface is exactly four names, the baseline fails, and mutmut aborts. Any
   introspection test needs the same treatment.
3. **Mutate the whole package, and set `pythonpath = ["src", "tests"]`.** With a `src/` layout and an
   editable install, mutating a single file leaves an incomplete namespace package that loses to the
   real one, and the tests silently run against unmutated source. Mutmut catches this and says *"no
   test covers any mutant"* rather than reporting a fake score — if you see that, this is why.

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

## Two rules for the harness itself

- **Never truncate silently.** A `tail -N` on the survivor list caps the count without saying so, and
  the capped number then gets reported as a total. Collect in full; truncate at display.
- **Verify the fix.** After adding tests, re-run and diff the survivor list *by name*, not by count —
  new code adds new mutants, so the count can rise while every targeted mutant died.
