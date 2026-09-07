# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow it going forward. Dates are ISO 8601 (YYYY-MM-DD).
Versions are git tags (`vX.Y.Z`) using [semver](https://semver.org/)'s
pre-release convention: `0.y.z` while the app's shape may still change with
any release; `1.0.0` when it stabilizes.

## [Unreleased]

### Added

- **A spent API key ends a question as a limit, and says whose limit it is.** Where
  the provider refuses a request for lack of credit, the question ends as
  `provider_limit` rather than as an indistinguishable `provider_failure`, and both
  drivers say that the remedy lies with whoever pays for the deployment — replacing
  the page's "start a new session" advice, which a spent key makes useless. Further
  questions are refused, since asking again cannot come out differently, and the
  request is no longer retried, because a key acquires no balance during a backoff.
  Whatever the answer had established before the refusal is kept rather than replaced
  by the notice ([ADR-0600]).

### Fixed

- **An ending that speaks for the agent is no longer reported as a bad answer.** Where
  a question stops on its spend ceiling, on an unpriceable response, on the retrieval
  bound, or with no answer at all, the sentence the reader sees is the agent's own —
  and it was being run through the citation and grounding checks, so a reader could be
  told "this answer is not grounded in the corpus" about a system notice, with
  `answer.ungrounded` written to the trail for a question the model never answered.
  What retrieval found is still reported: that is evidence, not a judgement about
  prose.
- **SciNumbers ask** — an agent answering natural-language questions about
  biological quantities from a supplied JSONL corpus, citing an entry for every
  number and saying it could not find one rather than answering from the model's
  own knowledge.
- **Two drivers over one agent** — a terminal (`scinumbers-ask`) and a web page
  (`streamlit run streamlit_app.py`), both rendering the same events. The agent is
  not told which is calling it.
- **Entries beside every answer** — cited first, then others the search found and
  the answer passed over, with the counts of what was retrieved and what matched.
- **Marks for what the source did not claim** — no measurement method, no scalar
  value, cited-but-not-retrieved, a bound or approximation reported as exact, two
  bounds that may be different quantities, and a range spanning more than a
  millionfold. Each is shown to the reader and told to the model.
- **Dimensional checking** — values are compared only where their units measure the
  same kind of thing, with an unrecognised unit reported as unknown rather than
  assumed compatible.
- **Sessions that survive a restart** — LangGraph checkpoints keyed by a session
  identifier published to the page's URL.
- **Limits said where they bind** — a per-question spend ceiling with a warning
  derived at 80 per cent, a run budget, a conversation bounded by token count, a
  model-call limit and a retrieval limit. Every question ends with a stated reason,
  what it cost, and which bounds it reached.
- **A warning when an answer is not grounded** — a citation to an entry no tool call
  returned, and an answer produced with no retrieval behind it.

### Known gaps

- No evaluation harness yet: nothing has been scored against expected answers, which
  is why the app describes itself as a prototype that is not scientifically
  trustworthy.

- **`bionumbers-ingest`** — a command that turns the published BioNumbers export
  (an HTML table served as `.xls`) into a JSONL corpus. The export is fetched by
  the reader and nothing derived from it is ever committed, so a corpus stops
  being an artefact only its author possesses ([ADR-0200]).
- **A manifest beside every corpus**, recording the source's checksum, size and
  modification time, when the run happened, which version ran, and every count
  from the report. Each record also carries twelve characters of that checksum.
  The export has no date or version anywhere in it, so without this two corpus
  files cannot be told apart or dated ([ADR-0240]).
- **A run report** of what could not be interpreted, with a count per flag —
  zeroes stated rather than omitted.
- **`range_fused`** on every record: the stored bounds may come from two
  different quantities, because bounds are the lowest and highest number in the
  cell. 1,418 records of the current export ([ADR-0230]).
- **`range_percent_deviation`** in `parse_flags` where the bounds came from a
  relative uncertainty: `±23%` is a fraction of the value, not a quantity, and
  reading it as one gave a 46-unit interval around a value of 0.488.
- **`range_one_sided`** and **`range_approximate`** on every record: which kind
  of hedge the source used, because the two need different words in front of a
  reader. 594 and 1,639 records; together they partition `range_qualified`.
- **`range_qualified`** on every record: the source did not state a closed
  interval. `<0.001` stored as the interval 0.001–0.001 asserts an exact equality
  where the source said *less than*. 2,233 records.
- **A resolver** that reports whether a corpus is present, or whether an export
  beside it could produce one, so a driver can offer to build it rather than
  failing with "no corpus at that path" while the export sits in the same
  directory. Reporting is separate from building, so the caller can say what is
  about to happen before a 27 MB read. A corpus that exists is never rebuilt.
- **The ingest operation refuses to run where git would track its output**, naming
  the repository, rather than writing unlicensed data onto a committable path. In
  the operation rather than the command, so every caller inherits it ([ADR-0250]).

### Changed

- **Citations are written `[[100002]]`.** The model was asked for `BNID 100002`, in
  a package no longer named for that database. The delimiters mean the parser has no
  rules about an identifier's shape left — the width floor, the run rule and the
  digit-count continuation existed only to infer where an identifier ended
  ([ADR-0410]). The prompt now produces the form from the parser's own definition
  instead of restating it, which it had done for the project's whole life with
  nothing tying the two together.
- The parser still accepts `BNID 100002`. Not for the model's sake — an entry
  rendered to it no longer contains that form — but for the reader's: someone who
  knows BioNumbers types it into a question, follow-ups inherit the conversation,
  and from then on answers are written in it. Rejecting it would mark those
  well-cited answers unsupported.
- **An entry's own cross-references are restated only where the model reads them.**
  BioNumbers writes `See BNID 102065, 104333` in its entry text; the copy handed to
  the model says `See [[102065]], [[104333]]`. The stored corpus and every surface a
  person sees keep the source's words, so an entry stays quotable and a view of the
  unprocessed record remains possible ([ADR-0420]). Rewriting at ingest was
  rejected for that reason.
- **The identifier field and corpus key are `entry_id`.** Still an integer;
  [ADR-0430] records what a widening to a string would touch rather than building
  for a source that does not exist yet.
- Trace records name `entry_id` and `entry_ids` where they named `bnid` and `bnids`.
  A `logs/trace.jsonl` written before this reads differently to anything parsing
  those keys.
- **Renamed to `scinumbers`.** The package is `scinumbers_ask`, the console script
  is `scinumbers-ask`, and the environment variables are `SCINUMBERS_*`. The app
  has called itself SciNumbers on every surface a reader sees since the README was
  written; the code now agrees ([ADR-0400]). `bionumbers-ingest` keeps its name —
  it is the BioNumbers adapter, and that is what it is called.
- A `BIONUMBERS_ASK_*` variable now **stops the run** and names its replacement,
  rather than being ignored. Ignoring one is configuration that silently stops
  being read — a ceiling that no longer binds, a run label that quietly becomes
  `dev` and mixes an evaluation's spend into a person's — and each of those looks
  like a working run.
- The whole export is processed by default; a row limit must be asked for and is
  recorded in the manifest. A sampled corpus looks complete and is not.
- The corpus appears at its destination only after the last record is written, so
  a failed run leaves the previous corpus or nothing — never a short one.
- JSONL is the only output format; the parquet output and `pyarrow` are dropped,
  since a second serialization path is a second place the contract can drift
  silently ([ADR-0220]).

### Fixed

Defects in the ported first-pass ingester, each of which produced a plausible
number rather than an error:

- Markup was stripped before entities were unescaped, and the export's injected
  markup arrives escaped — so the strip matched nothing, the unescape
  manufactured a live tag, and 10,206 of 14,294 records carried `<IMG …>` in
  their keywords while the flag meant to report it read **zero**, because its
  condition was unreachable.
- Any angle bracket was treated as markup, deleting scientific content: variable
  notation (`<D>`, `<Csat>`) and whole clauses after a less-than sign, including
  a p-value and a DOI fragment, out of `Comments`.
- `2×10^5` was read as three numbers and `150,000` as two, inflating the
  fused-range counts by nearly a third.
- The plus-or-minus deviation was the first number in the cell rather than the
  one after the sign, and 138 cells with more than one `±` collapsed into a
  single fabricated interval, unflagged.
- A hyphen after a unit was read as a sign, so `5%-10%` gave −10 to 5 on 203
  records; a number without a leading zero lost its decimal point on 20.
- Bounds written after a "Table link" URL were discarded on 10 records.
- Three cells wrote an exponent once for both bounds — `1-2×10^9 cells/ml` stored
  as 1 to 2,000,000,000 — now flagged rather than corrected.

[ADR-0410]: docs/decisions/0410-one-delimited-citation-form.md
[ADR-0420]: docs/decisions/0420-rewrite-notation-when-rendering.md
[ADR-0430]: docs/decisions/0430-the-entry-identifier-stays-an-integer.md
[ADR-0400]: docs/decisions/0400-the-package-is-named-for-the-question.md
[ADR-0200]: docs/decisions/0200-ship-an-ingester-not-a-prepared-corpus.md
[ADR-0210]: docs/decisions/0210-verifying-a-contract-owned-by-another-branch.md
[ADR-0220]: docs/decisions/0220-jsonl-only.md
[ADR-0230]: docs/decisions/0230-flag-and-count-never-correct.md
[ADR-0240]: docs/decisions/0240-stamp-every-ingest.md
[ADR-0250]: docs/decisions/0250-guards-belong-to-the-operation.md
[ADR-0600]: docs/decisions/0600-a-spent-key-is-its-own-ending.md
