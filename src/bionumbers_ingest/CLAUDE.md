# `bionumbers_ingest` — the corpus pipeline

Lives here rather than in the root `CLAUDE.md` because it is a warning for
someone about to change *this* package, and irrelevant to the two work packages
that never touch it. The root file is loaded into every session and every
subagent; this one is not.

A **pipeline**, and the shape is load-bearing: the two ends are the only modules that know a file
format, and nothing between them knows either.

| Module | Role |
|---|---|
| `parsing/html_table.py` | source format in — streams `<tr>` rows, preserving raw inner HTML |
| `cleaning.py` | one raw row → one record; the only place that unescapes or strips |
| `model.py` | the record, plus `EXPECTED_HEADERS` |
| `validation.py` | the run report |
| `provenance.py` | source fingerprint and manifest |
| `io.py` | JSONL out, renamed into place on success |
| `ingest.py` | wires the pipeline together |
| `guard.py` | the refusal to write where git would track the output |
| `resolve.py` | find a corpus, or the export that would produce one |
| `cli.py` | the command |

Five things about it that reading one module will not tell you:

- **The reader preserves raw HTML deliberately.** The export's injected markup arrives
  HTML-escaped, so a reader that unescaped would hand cleaning a live tag and destroy the evidence of
  which form the source used. Unescaping happens once, in `cleaning`, before markup is stripped.
- **An angle bracket is not evidence of markup.** The export contains exactly one HTML element and
  uses `<` as a less-than sign in prose. A tag is recognised only by a real HTML element name.
- **Records are buffered, not streamed, between cleaning and the writer**, because each carries a
  digest of the whole source, which is unknown until the last byte. Roughly 70 MB; ADR-0240.
- **Four booleans are the contract with `numera_ask`**, not the flag names: `range_fused`,
  `range_qualified`, `range_one_sided` and `range_approximate`. `parse_flags` is cleaning's own
  vocabulary and may change — the last two became fields because the consumer was reading them out of
  that list by name, where a rename would have turned them silently false. ADR-0230.
- **The git-tracking refusal is in `guard.py`, called by `ingest()`, not by the command.** It lived
  in `cli.py` and so protected one caller; the operation invoked as a library wrote 20 MB onto a
  committable path in silence. A guard in a driver is a guard for one
  driver; ADR-0250.
- **An unknown is a refusal.** When git is installed and gives no answer -- a timeout, a failure
  to start, any error but "not a git repository" -- `committable_repo_for` raises
  `GitDidNotAnswer` rather than returning `None`. It used to allow the write, and once let a
  results file into the repository under a loaded test run. Only "no repository" and "no git
  installed" pass; ADR-1800.
- **`cleaning.py` has been the densest source of defects in the project**, and every one of them
  produced a plausible number rather than an error. Seven review passes, fault seeding and mutation
  testing each found more; treat a change there as needing all three, and **measure both directions**
  — a fix that stops over-flagging usually starts under-flagging, and only the second is dangerous.

One more, learned while mutation-testing another module: **`guard.py` reads the
working tree it is standing in**, so a test that exercises it cannot be run from
a copy of the repository — the copy is not a git repository, `committable_repo_for`
correctly returns `None`, and the refusal never fires. That is the guard working,
not failing, and it has to be deselected rather than fixed. See the
`mutation-test-module` skill, gotcha 5.
