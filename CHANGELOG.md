# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow it going forward. Dates are ISO 8601 (YYYY-MM-DD).
Versions are git tags (`vX.Y.Z`) using [semver](https://semver.org/)'s
pre-release convention: `0.y.z` while the app's shape may still change with
any release; `1.0.0` when it stabilizes.

## [Unreleased]

### Added

- **BioNumbers ask** — an agent answering natural-language questions about
  biological quantities from a supplied JSONL corpus, citing an entry for every
  number and saying it could not find one rather than answering from the model's
  own knowledge.
- **Two drivers over one agent** — a terminal (`bionumbers-ask`) and a web page
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
