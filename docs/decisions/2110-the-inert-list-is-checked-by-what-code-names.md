# ADR-2110: The inert list is checked by what code names; selecting tests by name was rejected

- **Status:** accepted
- **Date:** 2026-11-24
- **Pull request:** none yet (`chore/cheaper-test-loop`)
- **Amends:** [ADR-1300](1300-two-tier-test-loop.md) (the two-tier test loop)

## Context

ADR-1300's commit tier leaves Python under `src/` and `tests/` to testmon, runs nothing for a
short inert list, and runs the **full suite** for every other staged file, because testmon cannot
see a test that merely reads a file. The inert list was backed by a tripwire that grepped test
files for each inert path as written (`".github/"`).

That tripwire was blind. `test_scheduled_workflows.py` reads every workflow through
`ROOT / ".github" / "workflows"`, so the string `.github/` never appears in it, and `.github/` sat
on the inert list while a test read it. A commit that changed only a workflow ran **no test**. The
push tier caught it later.

The commit tier was also the main cost of committing documents. Every edit to `README.md`,
`CLAUDE.md` or an OpenSpec spec ran the full suite (about 160 s).

## Decision

- **`.github/` leaves the inert list:** a workflow change runs the full suite. **`CLAUDE.md` joins
  it:** no tracked code names it, and it was committed often enough that a full run for each edit
  was a large share of the hook's cost.
- **The tripwire reads string literals, not text.** `tests/test_testloop.py` parses every tracked
  Python source and reads `bin/` shell scripts as text. It fails when any of them names an inert
  path as a path segment, wherever the segment stands in a string (`ROOT / ".github"`, `"ls
  .github/workflows"`, `b".github/x"`, a quoted path in a shell script). Docstrings and comments
  are prose and are skipped. Over-matching is the cheap direction here: a message that mentions
  `docs/roadmap.md` costs a `KNOWN_MENTIONS` line with its reason, never a missed reader. A canary
  asserts the tripwire still sees `test_scheduled_workflows.py` naming `.github`.
- **The rule for every other file is unchanged:** the full suite.

## Rejected: run only the test files that name a changed file

Tried on this branch and reverted before merging. For a changed non-Python file, the hook would
read the string literals of every tracked source and run only the `tests/test_*.py` files that
name it. It fell back to the full suite when the app, a script or a test helper named the file,
when nothing did, or when a tool read it. Measured on 2026-11-24 over 532 tracked files, it
narrowed 172 of them. A `README.md` commit took 45 s and an OpenSpec spec 11 s, against about
160 s.

It was rejected because **naming is not reading, and the two miss in different directions.** A
test that names a file without reading it only makes a run longer. But one incidental mention
also turns off the fallback that protects a file nothing names. Once any test names a file, every
*other* reader is assumed to name it too. A review of the branch found five ways a real reader
could be skipped, none triggered by the tree at the time but each one edit away:
- a dict key equal to a directory name (`counts["agents"]`) named every file under `.claude/agents/`
- test files that import fixtures from other test files
- quoted paths in shell scripts
- paths starting with a dot inside longer strings
- byte strings

Each could be patched, but patching narrows an open-ended list of ways a guess about reads can be
wrong. It does not close it.

If the speedup is wanted again, the sound version selects from **measured** reads. That means
recording which repository files each test opens (Python's audit hook) during the full runs at
push, and selecting from that map at commit. That is a separate work package, not a patch to
this one.

## Trade-off accepted

`README.md` and OpenSpec commits still run the full suite. A commit changing a workflow now runs
the full suite, where before it ran nothing. Both are the safe direction.

**What was verified.** Eight defects were seeded into a copy, with a green baseline, a caught
canary and a test inside the copy asserting that the copy was what ran. Two were in the hook:
`.github/` back on the inert list, and `CLAUDE.md` off it. Six were in the tripwire: grepping for
`token + "/"`, reading no files, losing the left segment boundary, reading docstrings, parsing
shell scripts as Python, and ignoring byte strings. Each was caught by the test named for it. The
first run let the shell-script seed survive, because the only shell case did not parse as Python
anyway. A case that does (`ls .github`) was added before the second run.

**Not verified:** that no code reads an inert path through a path no string spells out. The
tripwire cannot see such a read, by construction.
