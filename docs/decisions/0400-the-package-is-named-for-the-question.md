# ADR-0400: The package is named for the question, not for one source

- **Status:** accepted
- **Date:** 2026-08-31
- **Pull request:** _pending — chore/rename-to-scinumbers_

## Context

The app has called itself **SciNumbers** on every surface a reader sees — the README title, the
Streamlit page title, the CHANGELOG heading — since the reviewer-facing README was written. It
called itself `bionumbers_ask` everywhere a developer looks: the package, the console script, and
seven `BIONUMBERS_ASK_*` environment variables. The rename reached the presentation layer and
stopped.

The mismatch is not only untidy. BioNumbers is the first corpus this project tests its idea
against, and a purpose-built database is planned. The code has largely already shed the coupling
the name asserts: all five `add-ask-agent` capability specs are written source-agnostically ("the
corpus", "entries", "identifiers"), `repository.py` raises `"corpus contains repeated identifiers"`
rather than naming BNIDs, and `events.py` carries `cited` and `retrieved` with no source in sight.

Three options were on the table.

**Keep `bionumbers_ask`.** Zero churn. Rejected: the name is a claim about what the package is
bound to, and it is no longer true. A reader who wanted to add a second corpus would reasonably
conclude the package had to be rewritten rather than pointed elsewhere.

**Rename all three packages, including the validator.** `src/bionumbers/` and the `bionumbers`
console script would become `scinumbers` too, leaving no inconsistency. Rejected: that package is
owned by `feat/grounding-validator-cytoskeleton`, which has never merged. Renaming it would force a
conflict onto work this branch cannot see, and the conflict would land on someone else's diff.

**Rename the ask package only.** Chosen.

## Decision

`src/bionumbers_ask/` becomes `src/scinumbers_ask/`, the console script becomes `scinumbers-ask`,
and the seven environment variables take the `SCINUMBERS_*` prefix. A retired variable name is
**refused by name** — `NotConfigured`, naming its replacement — following the precedent already set
for `BIONUMBERS_ASK_WARN_USD` when the warning threshold was replaced by a ceiling (ADR-0180). A
spend limit that silently stops being read is worse than one that will not start.

`bionumbers_ingest` **keeps its name.** It parses a 27 MB HTML table published with an `.xls`
extension, strips an injected `<IMG SRC="/WF_SQL_XSRF.html">` that appears 20,411 times, and knows
six range notations and two micrometre glyphs. That is not a generic ingester with a
BioNumbers-flavoured name; it *is* the BioNumbers adapter, and naming it so is accurate rather than
coupled. A second source gets a second ingester beside it.

`src/bionumbers/` and its console script are untouched, and every substitution in this change was
scoped to an explicit path list rather than run over the tree.

Two things are renamed by hand rather than by substitution, because a mistake in either is silent:

- `agent.py`'s `_origin` matched `"bionumbers_ask" in name` against each frame's filename to find
  our own frames. It now matches the package directory computed from `__file__`. A literal there
  reports *no origin at all* after a rename — an internal error that says the fault is ours without
  saying where — and nothing raises. It happens to be covered by
  `test_the_trail_says_where_our_own_defect_was_raised`, but only by luck of that test asserting a
  filename rather than merely a non-crash.
- `trace.py`'s framework run-config tags every call `"bionumbers-ask"`. **Nothing asserted it.** A
  stale tag means a trail filtered by the new name comes back empty, with no fault reported
  anywhere. An assertion was added in the same commit as the rename.

## Trade-off accepted

The repository is still called BioNumbers, and `pyproject.toml`'s distribution name is still
`bionumbers` — so a reader meets three names before the code explains any of them. That
inconsistency is deliberate and temporary: the distribution rename churns `uv.lock`, which is
tracked, and touches a line the unmerged validator branch also edits. It is deferred rather than
resolved.

Renaming `web.py`'s Streamlit session-state keys drops any session in flight when the change lands.
Acceptable at one user, and sessions are cheap to restart.

Anyone with the old environment variables exported gets a refusal rather than a run. That is the
point, and it costs a one-line edit to fix.

The name **SciNumbers** is itself provisional — a display name is under consideration and may
change. Choosing the code identifier now, ahead of that, is deliberate: a display name lives in the
README and the page title and costs nothing to change, while a package name lives in git history,
ADRs, specs and every environment variable, and must not be changed twice.
